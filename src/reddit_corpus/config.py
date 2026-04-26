"""Config layer — TOML file + env vars + CLI overrides + sensible defaults.

Precedence (highest wins): env > CLI > file > built-in default.

The `to_dict()` method produces a redacted payload safe to log: secret fields
are replaced with `"***"` so a `--debug` dump never accidentally exposes a
refresh token.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import platformdirs

APP_NAME = "reddit-corpus"

_REQUIRED_REDDIT_FIELDS = ("client_id", "client_secret", "refresh_token", "user_agent")
_SECRET_FIELDS = frozenset({"client_id", "client_secret", "refresh_token"})


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class RedditAuth:
    client_id: str
    client_secret: str
    refresh_token: str
    user_agent: str


@dataclass(frozen=True, slots=True)
class IngestSettings:
    subreddits: tuple[str, ...] = ()
    listings: tuple[str, ...] = ("new",)
    more_expand_limit: int = 32


@dataclass(frozen=True, slots=True)
class Paths:
    db_path: Path


@dataclass(frozen=True, slots=True)
class Config:
    reddit: RedditAuth
    ingest: IngestSettings
    paths: Paths

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict with secrets redacted."""

        def _scrub(d: Mapping[str, Any]) -> dict[str, Any]:
            return {
                k: ("***" if k in _SECRET_FIELDS else _coerce(v)) for k, v in d.items()
            }

        def _coerce(v: Any) -> Any:
            if isinstance(v, Path):
                return str(v)
            if isinstance(v, tuple):
                return list(v)
            return v

        return {
            "reddit": _scrub(asdict(self.reddit)),
            "ingest": {k: _coerce(v) for k, v in asdict(self.ingest).items()},
            "paths": {k: _coerce(v) for k, v in asdict(self.paths).items()},
        }


def default_data_dir() -> Path:
    return Path(platformdirs.user_data_dir(APP_NAME))


def default_db_path() -> Path:
    return default_data_dir() / "corpus.db"


def load_config(
    env: Mapping[str, str],
    cli_overrides: Mapping[str, Any],
    file_path: Path,
) -> Config:
    """Resolve the runtime config from the four sources.

    `env` is typically `os.environ`. `cli_overrides` carries explicit `--client-id`
    style flags (their absence is encoded by simply not having the key). `file_path`
    is the absolute path to `config.toml`; it may be missing — in that case env
    must supply every required value.
    """
    file_data = _load_file(file_path)

    reddit_section = dict(file_data.get("reddit", {}))
    ingest_section = dict(file_data.get("ingest", {}))
    paths_section = dict(file_data.get("paths", {}))

    # Layer CLI over file (CLI keys flatten onto the reddit/auth section).
    for key in _REQUIRED_REDDIT_FIELDS:
        if key in cli_overrides and cli_overrides[key] is not None:
            reddit_section[key] = cli_overrides[key]

    # Layer env over CLI+file.
    env_map = {
        "client_id": env.get("REDDIT_CORPUS_CLIENT_ID"),
        "client_secret": env.get("REDDIT_CORPUS_CLIENT_SECRET"),
        "refresh_token": env.get("REDDIT_CORPUS_REFRESH_TOKEN"),
        "user_agent": env.get("REDDIT_CORPUS_USER_AGENT"),
    }
    for key, value in env_map.items():
        if value:
            reddit_section[key] = value

    missing = [k for k in _REQUIRED_REDDIT_FIELDS if not reddit_section.get(k)]
    if missing:
        raise ConfigError(
            "Missing required Reddit credentials: "
            + ", ".join(missing)
            + ". Set them in config.toml or via REDDIT_CORPUS_* env vars."
        )

    reddit = RedditAuth(
        client_id=str(reddit_section["client_id"]),
        client_secret=str(reddit_section["client_secret"]),
        refresh_token=str(reddit_section["refresh_token"]),
        user_agent=str(reddit_section["user_agent"]),
    )

    ingest = IngestSettings(
        subreddits=tuple(ingest_section.get("subreddits", ())),
        listings=tuple(ingest_section.get("listings", ("new",))),
        more_expand_limit=int(ingest_section.get("more_expand_limit", 32)),
    )

    db_value = paths_section.get("db_path", "default")
    db_path = _resolve_db_path(db_value, env=env)

    return Config(reddit=reddit, ingest=ingest, paths=Paths(db_path=db_path))


def _load_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Could not parse {path}: {exc}") from exc


def _resolve_db_path(file_value: Any, env: Mapping[str, str]) -> Path:
    env_db = env.get("REDDIT_CORPUS_DB")
    if env_db:
        return Path(env_db)
    if file_value == "default" or file_value is None:
        return default_db_path()
    return Path(str(file_value))


# Public helper: reapply just the secret-redaction step to an existing Config.
def redact(config: Config) -> Config:
    """Return a Config copy with all secret fields replaced with the literal '***'."""
    return replace(
        config,
        reddit=RedditAuth(
            client_id="***",
            client_secret="***",
            refresh_token="***",
            user_agent=config.reddit.user_agent,
        ),
    )


__all__ = [
    "APP_NAME",
    "Config",
    "ConfigError",
    "IngestSettings",
    "Paths",
    "RedditAuth",
    "default_data_dir",
    "default_db_path",
    "load_config",
    "redact",
]
