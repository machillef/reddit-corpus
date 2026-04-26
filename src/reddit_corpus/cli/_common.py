"""Helpers shared by the read-side CLI commands."""

from __future__ import annotations

import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import click

from reddit_corpus import config as cfg
from reddit_corpus.corpus import schema

_RELATIVE_RE = re.compile(r"^(\d+)([dhmw])$", re.IGNORECASE)
_UNIT_SECONDS = {
    "h": 3600,
    "d": 86_400,
    "w": 7 * 86_400,
    "m": 30 * 86_400,  # approximate; "month" rarely matters at this granularity
}


def parse_since(value: str | None) -> int | None:
    """Parse a `--since` value into a unix-second cutoff.

    Accepts either a relative form (`7d`, `24h`, `2w`) or an ISO date
    (`2026-04-01`, `2026-04-01T12:00:00`). Returns None when `value` is None.
    """
    if value is None:
        return None
    rel = _RELATIVE_RE.match(value.strip())
    if rel is not None:
        amount = int(rel.group(1))
        unit = rel.group(2).lower()
        seconds = amount * _UNIT_SECONDS[unit]
        return int(time.time()) - seconds
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise click.BadParameter(
            f"--since must be a relative duration (7d, 24h, 2w) or an ISO date "
            f"(YYYY-MM-DD). Got {value!r}."
        ) from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def default_config_file() -> Path:
    return cfg.default_data_dir() / "config.toml"


def load_config_or_exit(ctx: click.Context, config_path: str | None) -> cfg.Config:
    file_path = Path(config_path) if config_path else default_config_file()
    try:
        return cfg.load_config(env=os.environ, cli_overrides={}, file_path=file_path)
    except cfg.ConfigError as exc:
        click.echo(f"Config error: {exc}", err=True)
        ctx.exit(1)
        raise SystemExit(1)


def open_db_or_exit(ctx: click.Context, db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        click.echo(
            f"DB not found at {db_path}. Run `reddit-corpus init` first.",
            err=True,
        )
        ctx.exit(1)
        raise SystemExit(1)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    schema.apply_schema(conn)  # idempotent; ensures REGEXP function is registered
    return conn
