"""DAO tests for corpus.comments."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from typing import Any

import pytest

from reddit_corpus.corpus import comments as comments_dao
from reddit_corpus.corpus import posts as posts_dao
from reddit_corpus.corpus import schema
from reddit_corpus.reddit import Comment, Post


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    schema.apply_schema(c)
    c.execute(
        "INSERT INTO subreddits (name, display_name, first_seen_at) VALUES (?, ?, ?)",
        ("anthropic", "Anthropic", 1),
    )
    posts_dao.upsert_post(
        c,
        Post(
            id="p1",
            subreddit="anthropic",
            author="op",
            title="t",
            selftext="",
            url=None,
            score=1,
            num_comments=0,
            flair=None,
            created_utc=100,
            is_self=True,
            is_locked=False,
            removal_status="present",
            crosspost_parent_id=None,
            fetched_at=100,
        ),
    )
    yield c
    c.close()


def _comment(**overrides: Any) -> Comment:
    base: dict[str, Any] = {
        "id": "c1",
        "post_id": "p1",
        "parent_comment_id": None,
        "author": "alice",
        "body": "top-level reply",
        "score": 5,
        "created_utc": 200,
        "depth": 0,
        "removal_status": "present",
        "fetched_at": 200,
    }
    base.update(overrides)
    return Comment(**base)


def test_upsert_comments_inserts_top_level(conn):
    comments_dao.upsert_comments(conn, [_comment()])
    rows = list(conn.execute("SELECT id, parent_comment_id FROM comments"))
    assert len(rows) == 1
    assert rows[0]["id"] == "c1"
    assert rows[0]["parent_comment_id"] is None


def test_upsert_comments_inserts_nested(conn):
    parent = _comment(id="c1", parent_comment_id=None, depth=0)
    child = _comment(id="c2", parent_comment_id="c1", depth=1)
    comments_dao.upsert_comments(conn, [parent, child])
    rows = {
        r["id"]: r for r in conn.execute("SELECT id, parent_comment_id FROM comments")
    }
    assert rows["c1"]["parent_comment_id"] is None
    assert rows["c2"]["parent_comment_id"] == "c1"


def test_upsert_comments_updates_existing_row(conn):
    comments_dao.upsert_comments(conn, [_comment(score=5, fetched_at=200)])
    comments_dao.upsert_comments(conn, [_comment(score=42, fetched_at=999)])
    row = conn.execute(
        "SELECT score, fetched_at FROM comments WHERE id = 'c1'"
    ).fetchone()
    assert row["score"] == 42
    assert row["fetched_at"] == 999


def test_upsert_comments_rejects_orphan_via_fk(conn):
    """A comment whose parent_comment_id points at a non-existent comment fails FK."""
    orphan = _comment(id="orphan", parent_comment_id="ghost")
    with pytest.raises(sqlite3.IntegrityError):
        comments_dao.upsert_comments(conn, [orphan])


def test_walk_thread_returns_tree_walk_order(conn):
    """walk_thread returns rows ordered: parents before children, then by created_utc."""
    rows = [
        _comment(id="a", parent_comment_id=None, depth=0, created_utc=100),
        _comment(id="a1", parent_comment_id="a", depth=1, created_utc=110),
        _comment(id="a1a", parent_comment_id="a1", depth=2, created_utc=115),
        _comment(id="a2", parent_comment_id="a", depth=1, created_utc=120),
        _comment(id="b", parent_comment_id=None, depth=0, created_utc=200),
    ]
    comments_dao.upsert_comments(conn, rows)
    walked = comments_dao.walk_thread(conn, "p1")
    ids = [c.id for c in walked]
    assert ids[0] == "a"
    assert ids.index("a") < ids.index("a1") < ids.index("a1a")
    assert ids.index("a") < ids.index("a2")
    assert ids.index("b") > ids.index("a")
    assert {c.depth for c in walked if c.id == "a1a"} == {2}


def test_search_comments_matches_regex(conn):
    comments_dao.upsert_comments(
        conn,
        [
            _comment(id="c1", body="claude code rocks"),
            _comment(id="c2", body="totally unrelated"),
        ],
    )
    hits = comments_dao.search_comments(conn, sub="anthropic", pattern="claude")
    assert {c.id for c in hits} == {"c1"}


def test_search_comments_respects_limit(conn):
    rows = [_comment(id=f"c{i}", body="claude is here") for i in range(5)]
    comments_dao.upsert_comments(conn, rows)
    hits = comments_dao.search_comments(
        conn, sub="anthropic", pattern="claude", limit=2
    )
    assert len(hits) == 2


def test_walk_thread_appends_orphans_at_tail(conn):
    """A comment whose parent_comment_id is missing from the post is appended,
    not silently dropped from the read."""
    # Create a real parent and child first so FK is satisfied.
    comments_dao.upsert_comments(
        conn,
        [
            _comment(id="root", parent_comment_id=None, depth=0, created_utc=100),
            _comment(id="child", parent_comment_id="root", depth=1, created_utc=110),
        ],
    )
    # Manually insert an orphan whose parent is not in the DB. We bypass the DAO
    # because the DAO's FK enforcement would reject it; the orphan represents
    # the scenario where the parent comment was admin-deleted between fetches.
    # PRAGMA foreign_keys cannot change inside a transaction — commit first.
    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute(
        "INSERT INTO comments (id, post_id, parent_comment_id, author, body, "
        "score, created_utc, depth, removal_status, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "orphan",
            "p1",
            "ghost-parent",
            "u",
            "orphaned reply",
            1,
            200,
            2,
            "present",
            200,
        ),
    )
    conn.commit()
    conn.execute("PRAGMA foreign_keys = ON")
    walked = comments_dao.walk_thread(conn, "p1")
    ids = [c.id for c in walked]
    assert ids[:2] == ["root", "child"]
    assert ids[-1] == "orphan"


def test_walk_thread_handles_deeply_nested_threads(conn):
    """Iterative walk must not stack-overflow on threads deeper than Python's
    recursion limit (default 1000)."""
    depth = 1500
    chain = [_comment(id="c0", parent_comment_id=None, depth=0, created_utc=0)]
    for i in range(1, depth):
        chain.append(
            _comment(
                id=f"c{i}",
                parent_comment_id=f"c{i - 1}",
                depth=i,
                created_utc=i,
            )
        )
    comments_dao.upsert_comments(conn, chain)
    walked = comments_dao.walk_thread(conn, "p1")
    assert len(walked) == depth
    assert walked[0].id == "c0"
    assert walked[-1].id == f"c{depth - 1}"


def test_search_comments_filters_by_sub(conn):
    conn.execute(
        "INSERT INTO subreddits (name, display_name, first_seen_at) VALUES (?, ?, ?)",
        ("python", "Python", 1),
    )
    posts_dao.upsert_post(
        conn,
        Post(
            id="p2",
            subreddit="python",
            author="x",
            title="t",
            selftext="",
            url=None,
            score=1,
            num_comments=0,
            flair=None,
            created_utc=1,
            is_self=True,
            is_locked=False,
            removal_status="present",
            crosspost_parent_id=None,
            fetched_at=1,
        ),
    )
    comments_dao.upsert_comments(
        conn,
        [
            _comment(id="c_a", post_id="p1", body="claude here"),
            _comment(id="c_p", post_id="p2", body="claude there"),
        ],
    )
    hits = comments_dao.search_comments(conn, sub="anthropic", pattern="claude")
    assert {c.id for c in hits} == {"c_a"}
