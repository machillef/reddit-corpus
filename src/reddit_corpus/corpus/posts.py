"""DAO for the posts table."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from typing import Literal

from reddit_corpus.reddit import Post

SortKey = Literal["score", "created"]


# `ON CONFLICT … DO UPDATE` updates in place without deleting + re-inserting,
# avoiding FK-cascade fallout on `comments.post_id`. SQLite 3.24+ (we require 3.13).
_UPSERT = """
INSERT INTO posts (
    id, subreddit, author, title, selftext, url, score, num_comments, flair,
    created_utc, is_self, is_locked, removal_status, crosspost_parent_id, fetched_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET
    subreddit = excluded.subreddit,
    author = excluded.author,
    title = excluded.title,
    selftext = excluded.selftext,
    url = excluded.url,
    score = excluded.score,
    num_comments = excluded.num_comments,
    flair = excluded.flair,
    created_utc = excluded.created_utc,
    is_self = excluded.is_self,
    is_locked = excluded.is_locked,
    removal_status = excluded.removal_status,
    crosspost_parent_id = excluded.crosspost_parent_id,
    fetched_at = excluded.fetched_at
"""


def upsert_post(conn: sqlite3.Connection, post: Post) -> None:
    conn.execute(
        _UPSERT,
        (
            post.id,
            post.subreddit,
            post.author,
            post.title,
            post.selftext,
            post.url,
            post.score,
            post.num_comments,
            post.flair,
            post.created_utc,
            int(post.is_self),
            int(post.is_locked),
            post.removal_status,
            post.crosspost_parent_id,
            post.fetched_at,
        ),
    )


def get_post(conn: sqlite3.Connection, post_id: str) -> Post | None:
    row = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    if row is None:
        return None
    return _row_to_post(row)


# Explicit allowlist. The values are literal SQL fragments and never see user input;
# bypassing the dict lookup is the only way an unsafe value reaches the query string.
_SORT_FRAGMENTS: dict[str, str] = {
    "score": "ORDER BY score DESC, created_utc DESC",
    "created": "ORDER BY created_utc DESC",
}


def list_posts(
    conn: sqlite3.Connection,
    sub: str,
    *,
    since: int | None = None,
    top_n: int | None = None,
    sort: SortKey = "score",
) -> Sequence[Post]:
    order_clause = _SORT_FRAGMENTS.get(sort)
    if order_clause is None:
        raise ValueError(f"sort must be 'score' or 'created', got {sort!r}")

    where_clauses = ["subreddit = ?"]
    params: list[object] = [sub]
    if since is not None:
        where_clauses.append("created_utc >= ?")
        params.append(since)

    sql = f"SELECT * FROM posts WHERE {' AND '.join(where_clauses)} {order_clause}"
    if top_n is not None:
        sql += " LIMIT ?"
        params.append(top_n)

    rows = conn.execute(sql, params).fetchall()
    return [_row_to_post(r) for r in rows]


def _row_to_post(row: sqlite3.Row) -> Post:
    return Post(
        id=row["id"],
        subreddit=row["subreddit"],
        author=row["author"],
        title=row["title"],
        selftext=row["selftext"] or "",
        url=row["url"],
        score=row["score"],
        num_comments=row["num_comments"],
        flair=row["flair"],
        created_utc=row["created_utc"],
        is_self=bool(row["is_self"]),
        is_locked=bool(row["is_locked"]),
        removal_status=row["removal_status"],
        crosspost_parent_id=row["crosspost_parent_id"],
        fetched_at=row["fetched_at"],
    )
