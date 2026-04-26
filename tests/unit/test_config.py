"""Tests for reddit_corpus.config — precedence env > CLI > file > default."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from reddit_corpus import config as cfg


@pytest.fixture(autouse=True)
def _no_real_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Strip REDDIT_CORPUS_* env vars so each test starts hermetic."""
    for key in list(os.environ):
        if key.startswith("REDDIT_CORPUS_"):
            monkeypatch.delenv(key, raising=False)
    yield


def test_default_data_dir_is_a_path():
    p = cfg.default_data_dir()
    assert isinstance(p, Path)
    assert "reddit-corpus" in str(p).lower()


def test_default_db_path_is_under_data_dir():
    db = cfg.default_db_path()
    data = cfg.default_data_dir()
    assert isinstance(db, Path)
    assert data in db.parents or db.parent == data


def test_load_config_from_file(tmp_path: Path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        """
[reddit]
client_id = "id-from-file"
client_secret = "f1-sec"
refresh_token = "f1-tok"
user_agent = "ua-from-file"

[ingest]
subreddits = ["python"]
listings = ["new", "top:week"]
more_expand_limit = 16

[paths]
db_path = "default"
""",
        encoding="utf-8",
    )
    c = cfg.load_config(env={}, cli_overrides={}, file_path=cfg_file)
    assert c.reddit.client_id == "id-from-file"
    assert c.reddit.client_secret == "f1-sec"
    assert c.reddit.refresh_token == "f1-tok"
    assert c.reddit.user_agent == "ua-from-file"
    assert c.ingest.subreddits == ("python",)
    assert c.ingest.listings == ("new", "top:week")
    assert c.ingest.more_expand_limit == 16


def test_env_overrides_file_for_secrets(tmp_path: Path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        """
[reddit]
client_id = "from-file"
client_secret = "f2-sec"
refresh_token = "f2-tok"
user_agent = "ua-file"

[ingest]
subreddits = ["python"]
""",
        encoding="utf-8",
    )
    env = {
        "REDDIT_CORPUS_CLIENT_ID": "from-env",
        "REDDIT_CORPUS_CLIENT_SECRET": "from-env-secret",
    }
    c = cfg.load_config(env=env, cli_overrides={}, file_path=cfg_file)
    assert c.reddit.client_id == "from-env"
    assert c.reddit.client_secret == "from-env-secret"
    # values not overridden by env still come from the file
    assert c.reddit.refresh_token == "f2-tok"


def test_cli_overrides_beat_file_but_lose_to_env(tmp_path: Path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        """
[reddit]
client_id = "file-id"
client_secret = "f3-sec"
refresh_token = "f3-tok"
user_agent = "file-ua"
""",
        encoding="utf-8",
    )
    env = {"REDDIT_CORPUS_CLIENT_ID": "env-id"}
    cli_overrides = {"client_id": "cli-id", "user_agent": "cli-ua"}
    c = cfg.load_config(env=env, cli_overrides=cli_overrides, file_path=cfg_file)
    # env beats CLI beats file
    assert c.reddit.client_id == "env-id"
    # cli beats file
    assert c.reddit.user_agent == "cli-ua"


def test_malformed_toml_raises_config_error(tmp_path: Path):
    """A syntax error in config.toml must surface as ConfigError so the CLI's
    friendly handler catches it, not as a raw TOMLDecodeError traceback."""
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("this is = not valid = toml\n[", encoding="utf-8")
    with pytest.raises(cfg.ConfigError) as exc:
        cfg.load_config(env={}, cli_overrides={}, file_path=cfg_file)
    assert "config.toml" in str(exc.value)


def test_missing_required_secret_raises(tmp_path: Path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        """
[reddit]
client_id = "id"
# client_secret missing
refresh_token = "rtoken"
user_agent = "ua"
""",
        encoding="utf-8",
    )
    with pytest.raises(cfg.ConfigError) as exc:
        cfg.load_config(env={}, cli_overrides={}, file_path=cfg_file)
    assert "client_secret" in str(exc.value)


def test_missing_config_file_with_complete_env_works(tmp_path: Path):
    """With no config file at all, env can supply every required field."""
    env = {
        "REDDIT_CORPUS_CLIENT_ID": "id",
        "REDDIT_CORPUS_CLIENT_SECRET": "secret",
        "REDDIT_CORPUS_REFRESH_TOKEN": "rtoken",
        "REDDIT_CORPUS_USER_AGENT": "ua",
    }
    c = cfg.load_config(env=env, cli_overrides={}, file_path=tmp_path / "missing.toml")
    assert c.reddit.client_id == "id"
    assert c.ingest.subreddits == ()


def test_db_path_default_resolves_under_data_dir(tmp_path: Path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        """
[reddit]
client_id = "i"
client_secret = "s"
refresh_token = "r"
user_agent = "u"

[paths]
db_path = "default"
""",
        encoding="utf-8",
    )
    c = cfg.load_config(env={}, cli_overrides={}, file_path=cfg_file)
    assert c.paths.db_path == cfg.default_db_path()


def test_db_path_absolute_override(tmp_path: Path):
    cfg_file = tmp_path / "config.toml"
    custom_db = tmp_path / "custom.db"
    cfg_file.write_text(
        f"""
[reddit]
client_id = "i"
client_secret = "s"
refresh_token = "r"
user_agent = "u"

[paths]
db_path = "{custom_db.as_posix()}"
""",
        encoding="utf-8",
    )
    c = cfg.load_config(env={}, cli_overrides={}, file_path=cfg_file)
    assert c.paths.db_path == custom_db


def test_env_db_path_overrides_file(tmp_path: Path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        """
[reddit]
client_id = "i"
client_secret = "s"
refresh_token = "r"
user_agent = "u"

[paths]
db_path = "default"
""",
        encoding="utf-8",
    )
    custom = tmp_path / "env-override.db"
    c = cfg.load_config(
        env={"REDDIT_CORPUS_DB": str(custom)},
        cli_overrides={},
        file_path=cfg_file,
    )
    assert c.paths.db_path == custom


def test_config_is_json_serializable(tmp_path: Path):
    """The Config dataclass converts to JSON-friendly dict for debug logging."""
    env = {
        "REDDIT_CORPUS_CLIENT_ID": "secret-id-value",
        "REDDIT_CORPUS_CLIENT_SECRET": "secret-secret-value",
        "REDDIT_CORPUS_REFRESH_TOKEN": "secret-rtoken-value",
        "REDDIT_CORPUS_USER_AGENT": "ua-not-secret",
    }
    c = cfg.load_config(env=env, cli_overrides={}, file_path=tmp_path / "missing.toml")
    payload = c.to_dict()
    serialized = json.dumps(payload)
    # Keys remain so the dump shape is legible.
    assert "client_secret" in serialized
    # Secret VALUES are redacted.
    assert "secret-id-value" not in serialized
    assert "secret-secret-value" not in serialized
    assert "secret-rtoken-value" not in serialized
    # Non-secret values pass through.
    assert "ua-not-secret" in serialized
    # Paths section is rendered.
    assert "db_path" in serialized
    # Sanity: every secret slot is the literal redaction marker.
    assert payload["reddit"]["client_id"] == "***"
    assert payload["reddit"]["client_secret"] == "***"
    assert payload["reddit"]["refresh_token"] == "***"
