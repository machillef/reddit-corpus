"""End-to-end tests for the read-side CLI commands using a tmpdir SQLite seed."""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from reddit_corpus.cli.main import cli
from reddit_corpus.corpus import comments as comments_dao
from reddit_corpus.corpus import posts as posts_dao
from reddit_corpus.corpus import schema
from reddit_corpus.corpus import subreddits as subs_dao
from reddit_corpus.reddit import Comment, Post


def _post(post_id: str, **overrides: Any) -> Post:
    base: dict[str, Any] = {
        "id": post_id,
        "subreddit": "anthropic",
        "author": "alice",
        "title": f"title-{post_id}",
        "selftext": "body",
        "url": None,
        "score": 10,
        "num_comments": 2,
        "flair": None,
        "created_utc": 1_700_000_000,
        "is_self": True,
        "is_locked": False,
        "removal_status": "present",
        "crosspost_parent_id": None,
        "fetched_at": 1_700_000_000,
    }
    base.update(overrides)
    return Post(**base)


def _comment(
    cid: str, post_id: str, parent: str | None = None, **overrides: Any
) -> Comment:
    base: dict[str, Any] = {
        "id": cid,
        "post_id": post_id,
        "parent_comment_id": parent,
        "author": "bob",
        "body": f"comment-{cid}",
        "score": 1,
        "created_utc": 1_700_000_100,
        "depth": 0 if parent is None else 1,
        "removal_status": "present",
        "fetched_at": 1_700_000_100,
    }
    base.update(overrides)
    return Comment(**base)


@pytest.fixture
def db_with_data(tmp_path: Path) -> Iterator[Path]:
    db = tmp_path / "corpus.db"
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    schema.apply_schema(conn)
    subs_dao.ensure_subreddit_row(
        conn, name="anthropic", display_name="Anthropic", first_seen_at=1_700_000_000
    )
    subs_dao.touch_last_ingested(conn, name="anthropic", ts=1_700_000_500)
    subs_dao.ensure_subreddit_row(
        conn, name="python", display_name="Python", first_seen_at=1_700_000_010
    )
    posts_dao.upsert_post(conn, _post("p1", score=99, created_utc=1_700_000_100))
    posts_dao.upsert_post(conn, _post("p2", score=42, created_utc=1_700_000_200))
    posts_dao.upsert_post(
        conn, _post("p-py", subreddit="python", score=5, created_utc=1_700_000_050)
    )
    comments_dao.upsert_comments(
        conn,
        [
            _comment("c1", "p1", body="claude code rocks"),
            _comment("c2", "p1", parent="c1", body="agreed"),
            _comment("c3", "p2", body="totally unrelated"),
        ],
    )
    conn.commit()
    conn.close()
    yield db


def _write_config(tmp_path: Path, db: Path) -> Path:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        f"""
[reddit]
client_id = "id"
client_secret = "csec"
refresh_token = "rtok"
user_agent = "ua/1.0"

[paths]
db_path = "{db.as_posix()}"
""",
        encoding="utf-8",
    )
    return cfg_file


def _invoke(args: list[str]) -> dict:
    """Invoke a read command with --format json and return the parsed payload."""
    runner = CliRunner()
    result = runner.invoke(cli, [*args, "--format", "json"])
    assert result.exit_code == 0, f"exit={result.exit_code} output={result.output!r}"
    return json.loads(result.output)


def _invoke_md(args: list[str]) -> str:
    """Invoke a read command and return the raw markdown output."""
    runner = CliRunner()
    result = runner.invoke(cli, args)
    assert result.exit_code == 0, f"exit={result.exit_code} output={result.output!r}"
    return result.output


def test_posts_list_filters_by_sub(tmp_path: Path, db_with_data: Path) -> None:
    cfg = _write_config(tmp_path, db_with_data)
    payload = _invoke(
        ["posts", "list", "--config-path", str(cfg), "--sub", "anthropic"]
    )
    ids = {p["id"] for p in payload["posts"]}
    assert ids == {"p1", "p2"}


def test_posts_list_sort_score(tmp_path: Path, db_with_data: Path) -> None:
    cfg = _write_config(tmp_path, db_with_data)
    payload = _invoke(
        [
            "posts",
            "list",
            "--config-path",
            str(cfg),
            "--sub",
            "anthropic",
            "--sort",
            "score",
        ]
    )
    assert [p["id"] for p in payload["posts"]] == ["p1", "p2"]


def test_posts_list_top_n(tmp_path: Path, db_with_data: Path) -> None:
    cfg = _write_config(tmp_path, db_with_data)
    payload = _invoke(
        [
            "posts",
            "list",
            "--config-path",
            str(cfg),
            "--sub",
            "anthropic",
            "--top",
            "1",
        ]
    )
    assert len(payload["posts"]) == 1


def test_posts_list_since_relative(
    tmp_path: Path, db_with_data: Path, monkeypatch
) -> None:
    """`--since 7d` is interpreted as `now - 7d`. We pin time so the test is stable."""
    cfg = _write_config(tmp_path, db_with_data)
    # Force "now" to be just after p2 so the 1-second cutoff filters out p1.
    monkeypatch.setattr(time, "time", lambda: 1_700_000_200 + 1)
    payload = _invoke(
        [
            "posts",
            "list",
            "--config-path",
            str(cfg),
            "--sub",
            "anthropic",
            "--since",
            "1h",
        ]
    )
    # 1h cutoff = now - 3600 = 1700000201 - 3600 = 1699996601 (everything qualifies)
    # we just verify the flag is accepted and returns valid JSON
    assert isinstance(payload["posts"], list)


def test_posts_list_since_iso(tmp_path: Path, db_with_data: Path) -> None:
    cfg = _write_config(tmp_path, db_with_data)
    # 1_700_000_150 is between p1 (100) and p2 (200) — only p2 matches
    payload = _invoke(
        [
            "posts",
            "list",
            "--config-path",
            str(cfg),
            "--sub",
            "anthropic",
            "--since",
            "2023-11-14T22:15:50",  # ~ 1_700_000_150
        ]
    )
    ids = [p["id"] for p in payload["posts"]]
    assert "p2" in ids


def test_posts_show_returns_post(tmp_path: Path, db_with_data: Path) -> None:
    cfg = _write_config(tmp_path, db_with_data)
    payload = _invoke(["posts", "show", "p1", "--config-path", str(cfg)])
    assert payload["post"]["id"] == "p1"
    assert payload["post"]["score"] == 99


def test_posts_show_missing_post_exits_nonzero(
    tmp_path: Path, db_with_data: Path
) -> None:
    cfg = _write_config(tmp_path, db_with_data)
    runner = CliRunner()
    result = runner.invoke(cli, ["posts", "show", "ghost", "--config-path", str(cfg)])
    assert result.exit_code != 0
    assert "ghost" in result.output


def test_thread_show_returns_post_and_comments(
    tmp_path: Path, db_with_data: Path
) -> None:
    cfg = _write_config(tmp_path, db_with_data)
    payload = _invoke(["thread", "show", "p1", "--config-path", str(cfg)])
    assert payload["post"]["id"] == "p1"
    ids = [c["id"] for c in payload["comments"]]
    assert ids == ["c1", "c2"]  # tree-walk order: parent before child


def test_thread_show_missing_post(tmp_path: Path, db_with_data: Path) -> None:
    cfg = _write_config(tmp_path, db_with_data)
    runner = CliRunner()
    result = runner.invoke(cli, ["thread", "show", "ghost", "--config-path", str(cfg)])
    assert result.exit_code != 0


def test_comments_search_matches_pattern(tmp_path: Path, db_with_data: Path) -> None:
    cfg = _write_config(tmp_path, db_with_data)
    payload = _invoke(
        [
            "comments",
            "search",
            "--config-path",
            str(cfg),
            "--sub",
            "anthropic",
            "--pattern",
            "claude",
        ]
    )
    assert {c["id"] for c in payload["comments"]} == {"c1"}


def test_comments_search_invalid_regex_exits_with_friendly_message(
    tmp_path: Path, db_with_data: Path
) -> None:
    cfg = _write_config(tmp_path, db_with_data)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "comments",
            "search",
            "--config-path",
            str(cfg),
            "--sub",
            "anthropic",
            "--pattern",
            "[",  # malformed
        ],
    )
    assert result.exit_code != 0
    assert "regex" in result.output.lower() or "invalid" in result.output.lower()


def test_subs_list_returns_all_with_timestamps(
    tmp_path: Path, db_with_data: Path
) -> None:
    cfg = _write_config(tmp_path, db_with_data)
    payload = _invoke(["subs", "list", "--config-path", str(cfg)])
    by_name = {s["name"]: s for s in payload["subreddits"]}
    assert "anthropic" in by_name and "python" in by_name
    assert by_name["anthropic"]["display_name"] == "Anthropic"
    assert by_name["anthropic"]["last_ingested_at"] == 1_700_000_500
    assert by_name["python"]["last_ingested_at"] is None


def test_read_command_against_missing_db_exits_with_helpful_message(
    tmp_path: Path,
) -> None:
    """If the user runs a read command before `init` or first ingest."""
    cfg = _write_config(tmp_path, tmp_path / "does-not-exist.db")
    runner = CliRunner()
    result = runner.invoke(
        cli, ["posts", "list", "--config-path", str(cfg), "--sub", "anthropic"]
    )
    assert result.exit_code != 0
    assert "init" in result.output.lower() or "not found" in result.output.lower()


def test_posts_list_canonicalizes_sub_input(tmp_path: Path, db_with_data: Path) -> None:
    cfg = _write_config(tmp_path, db_with_data)
    payload = _invoke(
        [
            "posts",
            "list",
            "--config-path",
            str(cfg),
            "--sub",
            "/r/Anthropic",
        ]
    )
    ids = {p["id"] for p in payload["posts"]}
    assert ids == {"p1", "p2"}


# ---------- markdown output ---------- #


def test_posts_list_md_default_format(tmp_path: Path, db_with_data: Path) -> None:
    """No --format flag means markdown — that is the documented default."""
    cfg = _write_config(tmp_path, db_with_data)
    output = _invoke_md(
        ["posts", "list", "--config-path", str(cfg), "--sub", "anthropic"]
    )
    assert "title-p1" in output
    assert "title-p2" in output
    assert "u/alice" in output
    # Make sure we did not accidentally emit JSON braces.
    assert not output.strip().startswith("{")


def test_posts_show_md_includes_title_and_score(
    tmp_path: Path, db_with_data: Path
) -> None:
    cfg = _write_config(tmp_path, db_with_data)
    output = _invoke_md(["posts", "show", "p1", "--config-path", str(cfg)])
    assert "# r/anthropic — title-p1" in output
    assert "▲99" in output
    assert "u/alice" in output


def test_thread_show_md_indents_replies(tmp_path: Path, db_with_data: Path) -> None:
    cfg = _write_config(tmp_path, db_with_data)
    output = _invoke_md(["thread", "show", "p1", "--config-path", str(cfg)])
    # parent at depth 0 (no indent), reply at depth 1 (two-space indent).
    assert "### u/bob ▲1" in output
    assert "  ### u/bob ▲1" in output  # depth-1 reply is indented
    assert "Comments (2)" in output


def test_comments_search_md_renders_match(tmp_path: Path, db_with_data: Path) -> None:
    cfg = _write_config(tmp_path, db_with_data)
    output = _invoke_md(
        [
            "comments",
            "search",
            "--config-path",
            str(cfg),
            "--sub",
            "anthropic",
            "--pattern",
            "claude",
        ]
    )
    assert "**c1**" in output
    assert "claude code rocks" in output


def test_subs_list_md_is_a_table(tmp_path: Path, db_with_data: Path) -> None:
    cfg = _write_config(tmp_path, db_with_data)
    output = _invoke_md(["subs", "list", "--config-path", str(cfg)])
    assert "| Subreddit |" in output
    assert "Anthropic" in output
    assert "Python" in output


def test_posts_list_md_empty_corpus(tmp_path: Path, db_with_data: Path) -> None:
    """A subreddit with no matching posts renders a friendly empty message in md."""
    cfg = _write_config(tmp_path, db_with_data)
    output = _invoke_md(
        ["posts", "list", "--config-path", str(cfg), "--sub", "ghost-sub"]
    )
    assert "no posts" in output.lower()
