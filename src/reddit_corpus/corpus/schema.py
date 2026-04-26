"""SQLite schema for the corpus (v1).

The schema is the contract between ingest and query. v1 has no migration tooling:
if it changes, the user drops `corpus.db` and re-ingests. Acceptable at
personal-corpus scale.
"""

from __future__ import annotations

import re
import sqlite3

SCHEMA_VERSION = 1

CREATE_STATEMENTS: tuple[str, ...] = (
    "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL UNIQUE)",
    """
    CREATE TABLE IF NOT EXISTS subreddits (
        name TEXT PRIMARY KEY,
        display_name TEXT NOT NULL,
        first_seen_at INTEGER NOT NULL,
        last_ingested_at INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS posts (
        id TEXT PRIMARY KEY,
        subreddit TEXT NOT NULL REFERENCES subreddits(name),
        author TEXT,
        title TEXT NOT NULL,
        selftext TEXT,
        url TEXT,
        score INTEGER NOT NULL,
        num_comments INTEGER NOT NULL,
        flair TEXT,
        created_utc INTEGER NOT NULL,
        is_self INTEGER NOT NULL,
        is_locked INTEGER NOT NULL,
        removal_status TEXT NOT NULL CHECK (
            removal_status IN ('present','deleted_by_author','removed_by_mod','removed_other')
        ),
        crosspost_parent_id TEXT,
        fetched_at INTEGER NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS posts_sub_created ON posts(subreddit, created_utc DESC)",
    "CREATE INDEX IF NOT EXISTS posts_sub_score ON posts(subreddit, score DESC)",
    """
    CREATE INDEX IF NOT EXISTS posts_crosspost_parent
        ON posts(crosspost_parent_id)
        WHERE crosspost_parent_id IS NOT NULL
    """,
    """
    CREATE TABLE IF NOT EXISTS comments (
        id TEXT PRIMARY KEY,
        post_id TEXT NOT NULL REFERENCES posts(id),
        parent_comment_id TEXT REFERENCES comments(id) ON DELETE CASCADE,
        author TEXT,
        body TEXT NOT NULL,
        score INTEGER NOT NULL,
        created_utc INTEGER NOT NULL,
        depth INTEGER NOT NULL,
        removal_status TEXT NOT NULL CHECK (
            removal_status IN ('present','deleted_by_author','removed_by_mod','removed_other')
        ),
        fetched_at INTEGER NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS comments_post ON comments(post_id, created_utc)",
    "CREATE INDEX IF NOT EXISTS comments_parent ON comments(parent_comment_id)",
)


def _regexp(pattern: str, value: object) -> int:
    """SQLite REGEXP shim — propagates `re.error` so malformed patterns surface
    rather than silently returning empty results."""
    if value is None:
        return 0
    return 1 if re.search(pattern, str(value)) is not None else 0


def apply_schema(conn: sqlite3.Connection) -> None:
    """Apply the v1 schema if not already present, idempotently.

    Also turns on `PRAGMA foreign_keys = ON` (per-connection in SQLite) and
    registers a Python REGEXP function for the `comments search` command.
    """
    conn.execute("PRAGMA foreign_keys = ON")
    conn.create_function("REGEXP", 2, _regexp, deterministic=True)

    for stmt in CREATE_STATEMENTS:
        conn.execute(stmt)

    # `UNIQUE(version)` plus `INSERT OR IGNORE` makes this race-safe across
    # concurrent opens — duplicate inserts are silently dropped.
    conn.execute(
        "INSERT OR IGNORE INTO schema_version (version) VALUES (?)",
        (SCHEMA_VERSION,),
    )
    conn.commit()
