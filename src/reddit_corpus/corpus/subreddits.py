"""DAO for the subreddits table."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SubredditRow:
    name: str
    display_name: str
    first_seen_at: int
    last_ingested_at: int | None


def ensure_subreddit_row(
    conn: sqlite3.Connection,
    *,
    name: str,
    display_name: str,
    first_seen_at: int,
) -> None:
    """Insert if missing, otherwise refresh display_name only.

    `first_seen_at` is the timestamp of the *first* sighting; re-encounters do
    not update it. `display_name` does update because Reddit can change the
    preferred casing for a subreddit over time.
    """
    conn.execute(
        """
        INSERT INTO subreddits (name, display_name, first_seen_at)
        VALUES (?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET display_name = excluded.display_name
        """,
        (name, display_name, first_seen_at),
    )


def touch_last_ingested(
    conn: sqlite3.Connection,
    *,
    name: str,
    ts: int,
) -> None:
    """Set `last_ingested_at` to `ts` for the given subreddit."""
    conn.execute(
        "UPDATE subreddits SET last_ingested_at = ? WHERE name = ?",
        (ts, name),
    )


def list_subreddits(conn: sqlite3.Connection) -> Sequence[SubredditRow]:
    rows = conn.execute(
        "SELECT name, display_name, first_seen_at, last_ingested_at "
        "FROM subreddits ORDER BY name"
    ).fetchall()
    return [
        SubredditRow(
            name=r["name"],
            display_name=r["display_name"],
            first_seen_at=r["first_seen_at"],
            last_ingested_at=r["last_ingested_at"],
        )
        for r in rows
    ]
