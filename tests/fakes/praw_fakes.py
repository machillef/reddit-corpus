"""Hand-rolled PRAW shape fakes for unit tests.

Models the surface used by `reddit/client.py`, `reddit/ingest.pull_listing`,
and `reddit/ingest.expand_thread`. PRAW's real `Submission.comments` is a
`CommentForest`; we expose the same `.list()` and `.replace_more()` methods.
"""

from __future__ import annotations

import builtins
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field


@dataclass(slots=True)
class FakeAuthorRef:
    name: str | None


@dataclass(slots=True)
class FakeComment:
    """Stand-in for `praw.models.Comment`. `parent_id` is the Reddit-style
    fullname: `t3_<post_id>` for top-level replies, `t1_<comment_id>` for nested
    replies. `replies` is a flat list of direct child comments."""

    id: str
    body: str = ""
    score: int = 0
    created_utc: float = 0.0
    parent_id: str = ""
    author: FakeAuthorRef | None = field(default_factory=lambda: FakeAuthorRef("alice"))
    removed_by_category: str | None = None
    replies: list["FakeComment"] = field(default_factory=list)


@dataclass(slots=True)
class FakeMoreComments:
    """Stand-in for `praw.models.MoreComments` — the placeholder objects PRAW
    exposes in a forest until `replace_more()` is called."""

    id: str = "more"


@dataclass(slots=True)
class FakeCommentForest:
    """Mirrors `submission.comments` — supports `.list()` and `.replace_more()`.

    Field and return annotations use `builtins.list[...]` rather than `list[...]`
    because the class also defines a `list` *method* that mirrors PRAW's
    `CommentForest.list()`, which would otherwise shadow the builtin in
    annotation resolution.
    """

    top_level: builtins.list["FakeComment | FakeMoreComments"] = field(
        default_factory=builtins.list
    )
    replace_more_called_with: builtins.list[int | None] = field(
        default_factory=builtins.list
    )

    def replace_more(self, limit: int | None = 32) -> builtins.list[FakeMoreComments]:
        """Drop FakeMoreComments stubs from the forest (mimics PRAW's behavior).

        Records `limit` for assertions. Returns the list of stubs that were
        skipped (PRAW returns this so callers can see what wasn't expanded).
        """
        self.replace_more_called_with.append(limit)
        skipped: builtins.list[FakeMoreComments] = []
        kept: builtins.list[FakeComment | FakeMoreComments] = []
        for c in self.top_level:
            if isinstance(c, FakeMoreComments):
                skipped.append(c)
            else:
                kept.append(c)
        self.top_level = kept
        return skipped

    def list(self) -> builtins.list["FakeComment"]:
        """Flat tree-walk of the forest after replace_more.

        PRAW's CommentForest.list() traverses depth-first, parents before
        children. We do the same here.
        """
        out: builtins.list[FakeComment] = []

        def _walk(node: FakeComment) -> None:
            out.append(node)
            for child in node.replies:
                _walk(child)

        for top in self.top_level:
            if isinstance(top, FakeComment):
                _walk(top)
        return out


@dataclass(slots=True)
class FakeSubmission:
    """Subset of `praw.models.Submission` we read in pull_listing + expand_thread."""

    id: str
    title: str = "title"
    selftext: str = ""
    url: str | None = None
    score: int = 0
    num_comments: int = 0
    link_flair_text: str | None = None
    created_utc: float = 0.0
    is_self: bool = True
    locked: bool = False
    author: FakeAuthorRef | None = field(default_factory=lambda: FakeAuthorRef("alice"))
    removed_by_category: str | None = None
    crosspost_parent: str | None = None
    comments: FakeCommentForest = field(default_factory=FakeCommentForest)


@dataclass(slots=True)
class FakeListings:
    """Provides .new(limit=) / .top(time_filter, limit=) / .hot(limit=)."""

    submissions: list[FakeSubmission]

    def new(self, limit: int | None = None) -> Iterator[FakeSubmission]:
        return iter(self.submissions if limit is None else self.submissions[:limit])

    def hot(self, limit: int | None = None) -> Iterator[FakeSubmission]:
        return iter(self.submissions if limit is None else self.submissions[:limit])

    def top(
        self, time_filter: str = "all", limit: int | None = None
    ) -> Iterator[FakeSubmission]:
        _ = time_filter  # consumed by the parser; we don't filter here
        return iter(self.submissions if limit is None else self.submissions[:limit])


@dataclass(slots=True)
class FakeSubreddit:
    """Stand-in for `praw.models.Subreddit`."""

    display_name: str
    listings: FakeListings

    def new(self, limit: int | None = None) -> Iterator[FakeSubmission]:
        return self.listings.new(limit=limit)

    def hot(self, limit: int | None = None) -> Iterator[FakeSubmission]:
        return self.listings.hot(limit=limit)

    def top(
        self, time_filter: str = "all", limit: int | None = None
    ) -> Iterator[FakeSubmission]:
        return self.listings.top(time_filter=time_filter, limit=limit)


@dataclass(slots=True)
class FakeAuth:
    """Stand-in for `Reddit.auth` exposing `.limits` for ratelimit observation."""

    limits: dict[str, float | int | None] = field(
        default_factory=lambda: {
            "remaining": 99.0,
            "used": 1.0,
            "reset_timestamp": None,
        }
    )


@dataclass(slots=True)
class FakeReddit:
    """Stand-in for `praw.Reddit`. Configurable per-test."""

    subreddits: dict[str, FakeSubreddit] = field(default_factory=dict)
    auth: FakeAuth = field(default_factory=FakeAuth)
    me_username: str | None = "fake-bot"
    user_agent: str = "fake-ua"

    def subreddit(self, name: str) -> FakeSubreddit:
        # Mirror the real canonicalizer so tests exercising URL forms
        # ('https://reddit.com/r/foo') still find the configured fake.
        from reddit_corpus.reddit.client import canonicalize_subreddit

        canonical = canonicalize_subreddit(name)
        if canonical not in self.subreddits:
            raise KeyError(f"Unknown fake subreddit: {canonical}")
        return self.subreddits[canonical]

    class _UserCtx:
        def __init__(self, name: str | None) -> None:
            self._name = name

        def me(self) -> object:
            if self._name is None:
                # PRAW raises a 401-equivalent here; tests treat the exception type loosely.
                raise PermissionError("auth: no current user (token rejected)")
            return type("FakeUser", (), {"name": self._name})()

    @property
    def user(self) -> "FakeReddit._UserCtx":
        return FakeReddit._UserCtx(self.me_username)


def make_listings_from(*submissions: FakeSubmission) -> FakeListings:
    return FakeListings(submissions=list(submissions))


def make_fake_reddit_with(
    sub: str,
    submissions: Iterable[FakeSubmission],
    *,
    display_name: str | None = None,
) -> FakeReddit:
    from reddit_corpus.reddit.client import canonicalize_subreddit

    canonical = canonicalize_subreddit(sub)
    return FakeReddit(
        subreddits={
            canonical: FakeSubreddit(
                display_name=display_name or canonical.capitalize(),
                listings=make_listings_from(*submissions),
            )
        }
    )
