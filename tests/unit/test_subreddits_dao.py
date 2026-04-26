"""DAO tests for corpus.subreddits."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest

from reddit_corpus.corpus import schema
from reddit_corpus.corpus import subreddits as subs_dao


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    schema.apply_schema(c)
    yield c
    c.close()


def test_ensure_subreddit_row_inserts_when_missing(conn: sqlite3.Connection) -> None:
    subs_dao.ensure_subreddit_row(
        conn, name="anthropic", display_name="Anthropic", first_seen_at=100
    )
    row = conn.execute("SELECT * FROM subreddits WHERE name = 'anthropic'").fetchone()
    assert row is not None
    assert row["name"] == "anthropic"
    assert row["display_name"] == "Anthropic"
    assert row["first_seen_at"] == 100


def test_ensure_subreddit_row_is_idempotent(conn: sqlite3.Connection) -> None:
    subs_dao.ensure_subreddit_row(
        conn, name="anthropic", display_name="Anthropic", first_seen_at=100
    )
    subs_dao.ensure_subreddit_row(
        conn, name="anthropic", display_name="ANTHROPIC", first_seen_at=200
    )
    rows = conn.execute("SELECT * FROM subreddits").fetchall()
    assert len(rows) == 1
    # display_name updates on re-encounter (Reddit may rename a sub's preferred casing)
    assert rows[0]["display_name"] == "ANTHROPIC"
    # first_seen_at must NOT change on re-encounter — it's the first sighting only.
    assert rows[0]["first_seen_at"] == 100


def test_touch_last_ingested(conn: sqlite3.Connection) -> None:
    subs_dao.ensure_subreddit_row(
        conn, name="anthropic", display_name="Anthropic", first_seen_at=100
    )
    subs_dao.touch_last_ingested(conn, name="anthropic", ts=999)
    row = conn.execute(
        "SELECT last_ingested_at FROM subreddits WHERE name = 'anthropic'"
    ).fetchone()
    assert row["last_ingested_at"] == 999


def test_list_subreddits_returns_summary(conn: sqlite3.Connection) -> None:
    subs_dao.ensure_subreddit_row(
        conn, name="anthropic", display_name="Anthropic", first_seen_at=100
    )
    subs_dao.touch_last_ingested(conn, name="anthropic", ts=200)
    subs_dao.ensure_subreddit_row(
        conn, name="python", display_name="Python", first_seen_at=110
    )
    rows = subs_dao.list_subreddits(conn)
    by_name = {r.name: r for r in rows}
    assert by_name["anthropic"].display_name == "Anthropic"
    assert by_name["anthropic"].last_ingested_at == 200
    assert by_name["python"].last_ingested_at is None
