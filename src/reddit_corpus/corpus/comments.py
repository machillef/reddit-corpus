"""DAO for the comments table."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence

from reddit_corpus.reddit import Comment

_UPSERT = """
INSERT INTO comments (
    id, post_id, parent_comment_id, author, body, score, created_utc,
    depth, removal_status, fetched_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET
    post_id = excluded.post_id,
    parent_comment_id = excluded.parent_comment_id,
    author = excluded.author,
    body = excluded.body,
    score = excluded.score,
    created_utc = excluded.created_utc,
    depth = excluded.depth,
    removal_status = excluded.removal_status,
    fetched_at = excluded.fetched_at
"""


def upsert_comments(conn: sqlite3.Connection, items: Iterable[Comment]) -> None:
    """Insert or replace each comment in order.

    Caller must pass comments in tree-walk order (parents before children) so
    the FK on `parent_comment_id` is satisfied row by row at insert time.
    """
    for c in items:
        conn.execute(
            _UPSERT,
            (
                c.id,
                c.post_id,
                c.parent_comment_id,
                c.author,
                c.body,
                c.score,
                c.created_utc,
                c.depth,
                c.removal_status,
                c.fetched_at,
            ),
        )


def walk_thread(conn: sqlite3.Connection, post_id: str) -> Sequence[Comment]:
    """Return the post's comment tree in tree-walk order (parents then children).

    Implementation: pull all comments for the post once, group by parent, walk
    depth-first by `created_utc` within each level. Iterative on purpose — Reddit
    threads can nest beyond Python's default recursion limit (1000) and a
    `RecursionError` would mask a real read.
    """
    rows = conn.execute(
        "SELECT * FROM comments WHERE post_id = ? ORDER BY created_utc ASC",
        (post_id,),
    ).fetchall()
    children: dict[str | None, list[sqlite3.Row]] = {}
    for r in rows:
        children.setdefault(r["parent_comment_id"], []).append(r)

    out: list[Comment] = []
    # Stack holds rows still to process; pop pulls the most recently pushed,
    # so pushing children in reverse keeps left-to-right (created_utc-ascending) DFS order.
    stack: list[sqlite3.Row] = list(reversed(children.get(None, [])))
    while stack:
        row = stack.pop()
        out.append(_row_to_comment(row))
        kids = children.get(row["id"])
        if kids:
            stack.extend(reversed(kids))

    # Orphans: rows whose parent is not in this post's slice (e.g. parent was
    # admin-deleted between fetches). Append at the tail rather than dropping.
    seen = {c.id for c in out}
    for r in rows:
        if r["id"] not in seen:
            out.append(_row_to_comment(r))
    return out


def search_comments(
    conn: sqlite3.Connection,
    sub: str,
    pattern: str,
    *,
    limit: int = 50,
) -> Sequence[Comment]:
    """Regex search across comment bodies, scoped to a subreddit."""
    sql = """
        SELECT c.* FROM comments c
        JOIN posts p ON p.id = c.post_id
        WHERE p.subreddit = ? AND c.body REGEXP ?
        ORDER BY c.created_utc DESC
        LIMIT ?
    """
    rows = conn.execute(sql, (sub, pattern, limit)).fetchall()
    return [_row_to_comment(r) for r in rows]


def _row_to_comment(row: sqlite3.Row) -> Comment:
    return Comment(
        id=row["id"],
        post_id=row["post_id"],
        parent_comment_id=row["parent_comment_id"],
        author=row["author"],
        body=row["body"],
        score=row["score"],
        created_utc=row["created_utc"],
        depth=row["depth"],
        removal_status=row["removal_status"],
        fetched_at=row["fetched_at"],
    )
