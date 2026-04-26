"""Storage layer — pure operations over a sqlite3.Connection.

Never imports from `reddit.client` / `reddit.ingest`. Accepts and returns the
canonical `Post` / `Comment` dataclasses from `reddit_corpus.reddit`.
"""

from __future__ import annotations

from reddit_corpus.corpus import comments, posts, schema, subreddits

__all__ = ["comments", "posts", "schema", "subreddits"]
