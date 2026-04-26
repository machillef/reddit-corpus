"""Schema layer tests — applies and re-applies the v1 schema against :memory:."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest

from reddit_corpus.corpus import schema


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def test_apply_schema_creates_expected_tables(conn):
    schema.apply_schema(conn)
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    assert {"schema_version", "subreddits", "posts", "comments"} <= tables


def test_apply_schema_creates_expected_indexes(conn):
    schema.apply_schema(conn)
    indexes = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND name NOT LIKE 'sqlite_%'"
        )
    }
    assert "posts_sub_created" in indexes
    assert "posts_sub_score" in indexes
    assert "posts_crosspost_parent" in indexes
    assert "comments_post" in indexes
    assert "comments_parent" in indexes


def test_apply_schema_records_version(conn):
    schema.apply_schema(conn)
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    assert row["version"] == schema.SCHEMA_VERSION == 1


def test_apply_schema_idempotent(conn):
    schema.apply_schema(conn)
    schema.apply_schema(conn)
    rows = conn.execute("SELECT version FROM schema_version").fetchall()
    assert len(rows) == 1
    assert rows[0]["version"] == 1


def test_apply_schema_enables_foreign_keys(conn):
    schema.apply_schema(conn)
    fk_state = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk_state == 1


def test_removal_status_check_constraint_rejects_invalid_value(conn):
    schema.apply_schema(conn)
    conn.execute(
        "INSERT INTO subreddits (name, display_name, first_seen_at) VALUES (?, ?, ?)",
        ("anthropic", "Anthropic", 1),
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO posts (
                id, subreddit, title, score, num_comments, created_utc,
                is_self, is_locked, removal_status, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("p1", "anthropic", "t", 0, 0, 1, 1, 0, "bogus", 1),
        )


def test_search_comments_regex_function_registered(conn):
    """apply_schema must register a Python REGEXP function for SQLite."""
    schema.apply_schema(conn)
    row = conn.execute("SELECT 'claude code' REGEXP 'claude'").fetchone()
    assert row[0] == 1
    row = conn.execute("SELECT 'hello world' REGEXP 'claude'").fetchone()
    assert row[0] == 0


def test_regexp_propagates_re_error_for_malformed_pattern(conn):
    """A malformed regex must surface as an OperationalError instead of silently
    matching nothing — protects users from typo-driven empty result sets."""
    schema.apply_schema(conn)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("SELECT 'x' REGEXP '['").fetchone()
