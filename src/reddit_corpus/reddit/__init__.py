"""Network layer — PRAW client + dataclass models.

The `Post` and `Comment` dataclasses are the canonical types passed across the
`reddit → corpus → cli` boundary. PRAW's `praw.models.Submission` and
`praw.models.Comment` stay confined to `reddit/client.py` and `reddit/ingest.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RemovalStatus = Literal[
    "present", "deleted_by_author", "removed_by_mod", "removed_other"
]


@dataclass(frozen=True, slots=True)
class Post:
    """A Reddit post as stored in the corpus.

    Identity is `id` (Reddit base36). Subreddit is the canonical lowercase name.
    """

    id: str
    subreddit: str
    author: str | None
    title: str
    selftext: str
    url: str | None
    score: int
    num_comments: int
    flair: str | None
    created_utc: int
    is_self: bool
    is_locked: bool
    removal_status: RemovalStatus
    crosspost_parent_id: str | None
    fetched_at: int


@dataclass(frozen=True, slots=True)
class Comment:
    """A Reddit comment in tree-walk order.

    `parent_comment_id` is None for top-level replies (parent is the post itself);
    otherwise points at another `Comment.id` in the same post.
    """

    id: str
    post_id: str
    parent_comment_id: str | None
    author: str | None
    body: str
    score: int
    created_utc: int
    depth: int
    removal_status: RemovalStatus
    fetched_at: int


__all__ = ["Comment", "Post", "RemovalStatus"]
