"""Hand-rolled PRAW shape fakes for unit tests.

Only the surface used by `reddit/client.py` and `reddit/ingest.pull_listing` is
modeled. Comment-tree expansion fakes will land alongside Slice 6.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field


@dataclass(slots=True)
class FakeAuthorRef:
    name: str | None


@dataclass(slots=True)
class FakeSubmission:
    """The minimal subset of `praw.models.Submission` we read in pull_listing."""

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
    crosspost_parent: str | None = (
        None  # PRAW exposes a fullname like 't3_xxxxx' or omits the attr
    )


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
