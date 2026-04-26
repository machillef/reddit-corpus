"""Tests for `reddit-corpus auth test` (offline against fakes)."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from reddit_corpus.cli.main import cli
from tests.fakes.praw_fakes import FakeReddit


def _write_config(tmp_path: Path) -> Path:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        """
[reddit]
client_id = "id"
client_secret = "secret"
refresh_token = "rtoken"
user_agent = "ua/1.0"

[ingest]
subreddits = ["anthropic"]

[paths]
db_path = "default"
""",
        encoding="utf-8",
    )
    return cfg_file


def test_auth_test_prints_ok_and_exits_zero(tmp_path: Path):
    cfg_file = _write_config(tmp_path)
    fake = FakeReddit(me_username="real-user")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["auth", "test", "--config-path", str(cfg_file)],
        obj={"client_builder": lambda _config: fake},
    )
    assert result.exit_code == 0, result.output
    assert "OK" in result.output
    assert "real-user" in result.output


def test_auth_test_exits_nonzero_on_auth_failure(tmp_path: Path):
    cfg_file = _write_config(tmp_path)
    fake = FakeReddit(me_username=None)  # raises in user.me()

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["auth", "test", "--config-path", str(cfg_file)],
        obj={"client_builder": lambda _config: fake},
    )
    assert result.exit_code != 0
    assert "auth test failed" in result.output.lower()


def test_auth_test_exits_nonzero_on_missing_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        """
[reddit]
# missing all credentials
user_agent = "ua/1.0"
""",
        encoding="utf-8",
    )
    # Strip env to isolate from the host shell.
    for key in [
        "REDDIT_CORPUS_CLIENT_ID",
        "REDDIT_CORPUS_CLIENT_SECRET",
        "REDDIT_CORPUS_REFRESH_TOKEN",
        "REDDIT_CORPUS_USER_AGENT",
    ]:
        monkeypatch.delenv(key, raising=False)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["auth", "test", "--config-path", str(cfg_file)],
        obj={"client_builder": lambda _c: FakeReddit()},
    )
    assert result.exit_code != 0
    assert "config error" in result.output.lower()


def test_cli_root_help_lists_auth_group():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "auth" in result.output
