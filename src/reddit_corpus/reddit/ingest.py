"""Listing pull (no comment expansion in this slice).

`pull_listing(client, sub, listing_spec, fetched_at)` produces canonical `Post`
dataclasses from a (real or fake) PRAW client. Comment-tree expansion is
deferred to Slice 6.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from reddit_corpus.reddit import Post, RemovalStatus
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
