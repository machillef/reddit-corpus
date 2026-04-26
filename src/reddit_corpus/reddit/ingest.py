"""Listing pull and comment-tree expansion.

`pull_listing(client, sub, listing_spec, fetched_at)` produces canonical `Post`
dataclasses from a (real or fake) PRAW client.

`expand_thread(submission, sub_canonical, more_expand_limit, fetched_at)` calls
PRAW's `replace_more()` and walks the resulting comment forest, emitting a
flat list of `Comment` dataclasses in tree-walk order (parents before children)
so a sequential `upsert_comments` pass satisfies the FK on `parent_comment_id`
row by row.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from reddit_corpus.reddit import Comment, Post, RemovalStatus
from reddit_corpus.reddit.client import canonicalize_subreddit

_VALID_TOP_WINDOWS = frozenset({"hour", "day", "week", "month", "year", "all"})


def parse_listing_spec(spec: str) -> tuple[str, str | None]:
    """Parse `"new"` / `"hot"` / `"top[:WINDOW]"` into (sort, time_filter).

    `time_filter` is None for non-`top` sorts and `"all"` when no window is given.
    """
    if spec == "new":
        return "new", None
    if spec == "hot":
        return "hot", None
    if spec == "top":
        return "top", "all"
    if spec.startswith("top:"):
        window = spec.split(":", 1)[1]
        if window not in _VALID_TOP_WINDOWS:
            raise ValueError(
                f"Invalid top window: {window!r}. Expected one of {sorted(_VALID_TOP_WINDOWS)}."
            )
        return "top", window
    raise ValueError(
        f"Invalid listing spec: {spec!r}. Expected 'new', 'hot', or 'top[:WINDOW]'."
    )


_REMOVED_BY_CATEGORY_MAP: dict[str, RemovalStatus] = {
    # PRAW exposes these as Reddit's own category strings.
    "deleted": "deleted_by_author",
    "moderator": "removed_by_mod",
    "anti_evil_ops": "removed_by_mod",
    "automod_filtered": "removed_other",
    "reddit": "removed_other",
    "author": "deleted_by_author",
    "copyright_takedown": "removed_other",
}


def _map_removal_status(category: str | None) -> RemovalStatus:
    if category is None:
        return "present"
    return _REMOVED_BY_CATEGORY_MAP.get(category, "removed_other")


def _strip_fullname_prefix(fullname: str | None) -> str | None:
    """Reddit fullnames look like 't3_xxxxx'. We store the bare id."""
    if fullname is None:
        return None
    if "_" in fullname:
        return fullname.split("_", 1)[1]
    return fullname


def _author_name(author: Any) -> str | None:
    if author is None:
        return None
    name = getattr(author, "name", None)
    return name if isinstance(name, str) else None


def _submission_to_post(submission: Any, sub: str, fetched_at: int) -> Post:
    return Post(
        id=submission.id,
        subreddit=sub,
        author=_author_name(submission.author),
        title=submission.title,
        selftext=submission.selftext or "",
        url=getattr(submission, "url", None),
        score=int(submission.score),
        num_comments=int(submission.num_comments),
        flair=getattr(submission, "link_flair_text", None),
        created_utc=int(submission.created_utc),
        is_self=bool(getattr(submission, "is_self", True)),
        is_locked=bool(getattr(submission, "locked", False)),
        removal_status=_map_removal_status(
            getattr(submission, "removed_by_category", None)
        ),
        crosspost_parent_id=_strip_fullname_prefix(
            getattr(submission, "crosspost_parent", None)
        ),
        fetched_at=fetched_at,
    )


def pull_listing(
    client: Any,
    sub: str,
    listing_spec: str,
    *,
    fetched_at: int,
    limit: int | None = None,
) -> Iterator[Post]:
    """Yield `Post` dataclasses for `sub` under `listing_spec`.

    The client may be a real `praw.Reddit` or a `FakeReddit`-shape object —
    we only call documented PRAW surface (`reddit.subreddit(name).new()`,
    `.hot()`, `.top(time_filter=)`).
    """
    sort, time_filter = parse_listing_spec(listing_spec)
    canonical = canonicalize_subreddit(sub)
    subreddit_obj = client.subreddit(canonical)

    if sort == "new":
        submissions = subreddit_obj.new(limit=limit)
    elif sort == "hot":
        submissions = subreddit_obj.hot(limit=limit)
    else:
        submissions = subreddit_obj.top(time_filter=time_filter, limit=limit)

    for submission in submissions:
        yield _submission_to_post(submission, canonical, fetched_at)


def expand_thread(
    submission: Any,
    *,
    sub_canonical: str,
    fetched_at: int,
    more_expand_limit: int | None = 32,
) -> tuple[Post, list[Comment]]:
    """Expand a Submission's comment forest and emit a flat tree-walk-ordered list.

    Calls `submission.comments.replace_more(limit=more_expand_limit)` to drop
    `MoreComments` placeholder stubs (PRAW's argument is the maximum number of
    such stubs to expand, not a tree-depth cap). Then walks the surviving
    forest depth-first, parents before children, emitting `Comment`
    dataclasses with `(id, post_id, parent_comment_id, depth, ...)`.

    Top-level comments have `parent_comment_id = None` (their parent is the
    post itself, captured separately in the `post_id` column). Nested
    comments have `parent_comment_id` set to the bare comment id (the
    `t1_` fullname prefix is stripped).

    If a comment's `parent_id` does not resolve to another comment in the
    forest (e.g. its parent was a MoreComments stub that wasn't expanded),
    the comment is still emitted with `parent_comment_id = None` and depth
    capped at 0 — the caller should be tolerant of these orphans.
    """
    submission.comments.replace_more(limit=more_expand_limit)

    flat = list(submission.comments.list())
    by_id = {c.id: c for c in flat}
    post_fullname = f"t3_{submission.id}"

    out: list[Comment] = []
    depth_cache: dict[str, int] = {}

    def _resolve_depth_and_parent(c: Any) -> tuple[int, str | None]:
        parent_fullname = getattr(c, "parent_id", "") or ""
        if parent_fullname == post_fullname:
            return 0, None
        if parent_fullname.startswith("t1_"):
            parent_id = parent_fullname[len("t1_") :]
            if parent_id in by_id:
                parent_depth = depth_cache.get(parent_id)
                if parent_depth is None:
                    parent_depth, _ = _resolve_depth_and_parent(by_id[parent_id])
                    depth_cache[parent_id] = parent_depth
                return parent_depth + 1, parent_id
        # Orphan: parent comment is not in the local forest. Emit at depth 0.
        return 0, None

    for c in flat:
        depth, parent = _resolve_depth_and_parent(c)
        depth_cache[c.id] = depth
        out.append(
            Comment(
                id=c.id,
                post_id=submission.id,
                parent_comment_id=parent,
                author=_author_name(getattr(c, "author", None)),
                body=getattr(c, "body", "") or "",
                score=int(getattr(c, "score", 0)),
                created_utc=int(getattr(c, "created_utc", 0)),
                depth=depth,
                removal_status=_map_removal_status(
                    getattr(c, "removed_by_category", None)
                ),
                fetched_at=fetched_at,
            )
        )

    post = _submission_to_post(submission, sub_canonical, fetched_at)
    return post, out
