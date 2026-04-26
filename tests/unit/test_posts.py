"""DAO tests for corpus.posts."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from typing import Any, cast

import pytest

from reddit_corpus.corpus import posts as posts_dao
from reddit_corpus.corpus import schema
from reddit_corpus.reddit import Post


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    schema.apply_schema(c)
    c.execute(
        "INSERT INTO subreddits (name, display_name, first_seen_at) VALUES (?, ?, ?)",
        ("anthropic", "Anthropic", 1_700_000_000),
    )
    yield c
    c.close()


def _post(**overrides: Any) -> Post:
    base: dict[str, Any] = {
        "id": "p1",
        "subreddit": "anthropic",
        "author": "alice",
        "title": "Hello",
        "selftext": "body",
        "url": "https://reddit.com/r/anthropic/comments/p1",
        "score": 10,
        "num_comments": 2,
        "flair": None,
        "created_utc": 1_700_000_100,
        "is_self": True,
        "is_locked": False,
        "removal_status": "present",
        "crosspost_parent_id": None,
        "fetched_at": 1_700_000_200,
    }
    base.update(overrides)
    return Post(**base)


def test_upsert_post_inserts_new_row(conn: sqlite3.Connection) -> None:
    posts_dao.upsert_post(conn, _post())
    row = posts_dao.get_post(conn, "p1")
    assert row is not None
    assert row.id == "p1"
    assert row.score == 10


def test_upsert_post_updates_score_and_fetched_at(conn: sqlite3.Connection) -> None:
    posts_dao.upsert_post(conn, _post(score=10, fetched_at=1))
    posts_dao.upsert_post(conn, _post(score=42, fetched_at=999))
    row = posts_dao.get_post(conn, "p1")
    assert row is not None
    assert row.score == 42
    assert row.fetched_at == 999


def test_upsert_post_rejects_unknown_subreddit_via_fk(conn: sqlite3.Connection) -> None:
    bad = _post(subreddit="ghost")
    with pytest.raises(sqlite3.IntegrityError):
        posts_dao.upsert_post(conn, bad)


def test_get_post_returns_none_when_missing(conn: sqlite3.Connection) -> None:
    assert posts_dao.get_post(conn, "missing") is None


def test_list_posts_filters_by_sub(conn: sqlite3.Connection) -> None:
    posts_dao.upsert_post(conn, _post(id="p1", subreddit="anthropic"))
    conn.execute(
        "INSERT INTO subreddits (name, display_name, first_seen_at) VALUES (?, ?, ?)",
        ("python", "Python", 1),
    )
    posts_dao.upsert_post(conn, _post(id="p2", subreddit="python"))
    rows = posts_dao.list_posts(conn, sub="anthropic")
    assert [r.id for r in rows] == ["p1"]


def test_list_posts_respects_since(conn: sqlite3.Connection) -> None:
    posts_dao.upsert_post(conn, _post(id="old", created_utc=100))
    posts_dao.upsert_post(conn, _post(id="new", created_utc=900))
    rows = posts_dao.list_posts(conn, sub="anthropic", since=500)
    assert [r.id for r in rows] == ["new"]


def test_list_posts_sort_by_score_desc(conn: sqlite3.Connection) -> None:
    posts_dao.upsert_post(conn, _post(id="lo", score=1))
    posts_dao.upsert_post(conn, _post(id="hi", score=99))
    rows = posts_dao.list_posts(conn, sub="anthropic", sort="score")
    assert [r.id for r in rows] == ["hi", "lo"]


def test_list_posts_sort_by_created_desc(conn: sqlite3.Connection) -> None:
    posts_dao.upsert_post(conn, _post(id="old", created_utc=100))
    posts_dao.upsert_post(conn, _post(id="new", created_utc=900))
    rows = posts_dao.list_posts(conn, sub="anthropic", sort="created")
    assert [r.id for r in rows] == ["new", "old"]


def test_list_posts_top_n_caps_results(conn: sqlite3.Connection) -> None:
    for i in range(5):
        posts_dao.upsert_post(conn, _post(id=f"p{i}", score=i))
    rows = posts_dao.list_posts(conn, sub="anthropic", sort="score", top_n=2)
    assert len(rows) == 2
    assert rows[0].id == "p4"


def test_list_posts_invalid_sort_raises(conn: sqlite3.Connection) -> None:
    with pytest.raises(ValueError):
        # Cast around the Literal type — we're deliberately exercising the runtime check.
        posts_dao.list_posts(conn, sub="anthropic", sort=cast(Any, "banana"))


def test_upsert_post_handles_null_author(conn: sqlite3.Connection) -> None:
    posts_dao.upsert_post(conn, _post(author=None))
    row = posts_dao.get_post(conn, "p1")
    assert row is not None
    assert row.author is None


def test_upsert_post_preserves_crosspost_parent(conn: sqlite3.Connection) -> None:
    posts_dao.upsert_post(conn, _post(crosspost_parent_id="x123"))
    row = posts_dao.get_post(conn, "p1")
    assert row is not None
    assert row.crosspost_parent_id == "x123"


def test_re_upsert_post_with_existing_comments_does_not_cascade_delete(
    conn: sqlite3.Connection,
) -> None:
    """Regression test: under PRAGMA foreign_keys=ON, the original
    INSERT OR REPLACE would DELETE+INSERT the post row, which would either fail
    the FK or cascade-delete its comments. We use ON CONFLICT DO UPDATE instead."""
    from reddit_corpus.corpus import comments as comments_dao
    from reddit_corpus.reddit import Comment

    posts_dao.upsert_post(conn, _post(score=1, fetched_at=1))
    comments_dao.upsert_comments(
        conn,
        [
            Comment(
                id="c1",
                post_id="p1",
                parent_comment_id=None,
                author="u",
                body="reply",
                score=1,
                created_utc=2,
                depth=0,
                removal_status="present",
                fetched_at=2,
            )
        ],
    )
    # Re-upsert with new score — must not cascade-delete the comment.
    posts_dao.upsert_post(conn, _post(score=99, fetched_at=999))
    row = posts_dao.get_post(conn, "p1")
    assert row is not None
    assert row.score == 99
    remaining = conn.execute(
        "SELECT COUNT(*) FROM comments WHERE id = 'c1'"
    ).fetchone()[0]
    assert remaining == 1
