"""Tests for `reddit-corpus ingest`."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from click.testing import CliRunner

from reddit_corpus.cli.main import cli
from tests.fakes.praw_fakes import (
    FakeAuthorRef,
    FakeComment,
    FakeCommentForest,
    FakeReddit,
    FakeSubmission,
    make_fake_reddit_with,
)


def _write_config(
    tmp_path: Path, *, db: Path, subreddits: list[str], listings: list[str]
) -> Path:
    cfg_file = tmp_path / "config.toml"
    subs_quoted = ", ".join(f'"{s}"' for s in subreddits)
    listings_quoted = ", ".join(f'"{spec}"' for spec in listings)
    cfg_file.write_text(
        f"""
[reddit]
client_id = "id"
client_secret = "csec"
refresh_token = "rtok"
user_agent = "ua/1.0"

[ingest]
subreddits = [{subs_quoted}]
listings = [{listings_quoted}]
more_expand_limit = 32

[paths]
db_path = "{db.as_posix()}"
""",
        encoding="utf-8",
    )
    return cfg_file


def _submission_with_thread(post_id: str, body: str = "hello") -> FakeSubmission:
    return FakeSubmission(
        id=post_id,
        title=f"title-{post_id}",
        selftext=body,
        score=5,
        num_comments=1,
        created_utc=1_700_000_000,
        author=FakeAuthorRef("alice"),
        comments=FakeCommentForest(
            top_level=[
                FakeComment(
                    id=f"c-{post_id}",
                    body=f"reply to {post_id}",
                    parent_id=f"t3_{post_id}",
                    score=1,
                    created_utc=1_700_000_100,
                    author=FakeAuthorRef("bob"),
                ),
            ]
        ),
    )


def test_ingest_writes_posts_and_comments(tmp_path: Path) -> None:
    db = tmp_path / "corpus.db"
    cfg = _write_config(tmp_path, db=db, subreddits=["anthropic"], listings=["new"])
    fake = make_fake_reddit_with(
        "anthropic",
        [_submission_with_thread("p1"), _submission_with_thread("p2")],
        display_name="Anthropic",
    )
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["ingest", "--config-path", str(cfg)],
        obj={"client_builder": lambda _config: fake},
    )
    assert result.exit_code == 0, result.output

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    posts = conn.execute("SELECT id, title FROM posts ORDER BY id").fetchall()
    comments = conn.execute("SELECT id, post_id FROM comments ORDER BY id").fetchall()
    sub = conn.execute(
        "SELECT name, display_name, last_ingested_at FROM subreddits"
    ).fetchone()
    conn.close()

    assert {r["id"] for r in posts} == {"p1", "p2"}
    assert {r["id"] for r in comments} == {"c-p1", "c-p2"}
    assert sub["name"] == "anthropic"
    assert sub["display_name"] == "Anthropic"
    assert sub["last_ingested_at"] is not None


def test_ingest_creates_db_and_schema_when_missing(tmp_path: Path) -> None:
    """First run on a fresh host should create the DB file + schema, not fail."""
    db = tmp_path / "fresh.db"
    assert not db.exists()
    cfg = _write_config(tmp_path, db=db, subreddits=["anthropic"], listings=["new"])
    fake = make_fake_reddit_with("anthropic", [_submission_with_thread("p1")])
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["ingest", "--config-path", str(cfg)],
        obj={"client_builder": lambda _config: fake},
    )
    assert result.exit_code == 0, result.output
    assert db.exists()


def test_ingest_sub_override(tmp_path: Path) -> None:
    """--sub overrides config.subreddits for a single run."""
    db = tmp_path / "corpus.db"
    cfg = _write_config(
        tmp_path, db=db, subreddits=["should-not-be-used"], listings=["new"]
    )
    fake = make_fake_reddit_with("python", [_submission_with_thread("p1")])
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["ingest", "--config-path", str(cfg), "--sub", "python"],
        obj={"client_builder": lambda _config: fake},
    )
    assert result.exit_code == 0, result.output

    conn = sqlite3.connect(db)
    name = conn.execute("SELECT name FROM subreddits").fetchone()[0]
    conn.close()
    assert name == "python"


def test_ingest_listings_override(tmp_path: Path) -> None:
    """--listings overrides config.listings."""
    db = tmp_path / "corpus.db"
    cfg = _write_config(tmp_path, db=db, subreddits=["anthropic"], listings=["new"])
    fake = make_fake_reddit_with("anthropic", [_submission_with_thread("p1")])
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["ingest", "--config-path", str(cfg), "--listings", "top:week"],
        obj={"client_builder": lambda _config: fake},
    )
    assert result.exit_code == 0, result.output


def test_ingest_dry_run_does_not_write(tmp_path: Path) -> None:
    db = tmp_path / "corpus.db"
    cfg = _write_config(tmp_path, db=db, subreddits=["anthropic"], listings=["new"])
    fake = make_fake_reddit_with("anthropic", [_submission_with_thread("p1")])
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["ingest", "--config-path", str(cfg), "--dry-run"],
        obj={"client_builder": lambda _config: fake},
    )
    assert result.exit_code == 0, result.output
    # DB may have been opened (schema created) but no posts/comments written
    if db.exists():
        conn = sqlite3.connect(db)
        n_posts = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        conn.close()
        assert n_posts == 0


def test_ingest_per_post_failure_is_isolated(tmp_path: Path) -> None:
    """A single bad post shouldn't kill the run; the next post should still write."""
    import builtins

    db = tmp_path / "corpus.db"
    cfg = _write_config(tmp_path, db=db, subreddits=["anthropic"], listings=["new"])
    bad = _submission_with_thread("p1")

    # Make expand_thread blow up for p1 only by sabotaging .comments.list().
    # We assign via setattr() so ty doesn't reject the duck-typed swap.
    class _Boom:
        def replace_more(self, limit: int | None = 32) -> builtins.list[object]:
            _ = limit
            return []

        def list(self) -> builtins.list[object]:
            raise RuntimeError("simulated PRAW failure on p1")

    setattr(bad, "comments", _Boom())

    good = _submission_with_thread("p2")
    fake = make_fake_reddit_with("anthropic", [bad, good])
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["ingest", "--config-path", str(cfg)],
        obj={"client_builder": lambda _config: fake},
    )
    assert result.exit_code == 0, result.output

    conn = sqlite3.connect(db)
    ids = {r[0] for r in conn.execute("SELECT id FROM posts")}
    conn.close()
    assert ids == {"p2"}  # p1 failed and was skipped; p2 still made it


def test_ingest_handles_empty_subreddit_list_with_no_override(tmp_path: Path) -> None:
    """If no subs are configured and no --sub is passed, ingest exits with a helpful error."""
    db = tmp_path / "corpus.db"
    cfg = _write_config(tmp_path, db=db, subreddits=[], listings=["new"])
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["ingest", "--config-path", str(cfg)],
        obj={"client_builder": lambda _config: FakeReddit()},
    )
    assert result.exit_code != 0
    assert "no subreddits" in result.output.lower()
