"""`reddit-corpus auth ...` command group.

Currently exposes a single `auth test` that verifies Reddit OAuth credentials
by asking the live API for the authenticated user's identity.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import click

from reddit_corpus import config as cfg
from reddit_corpus.reddit.client import build_client

ClientBuilder = Callable[[cfg.Config], Any]


@click.group()
def auth_group() -> None:
    """OAuth-related commands."""


@auth_group.command("test")
@click.option(
    "--config-path",
    type=click.Path(dir_okay=False, path_type=str),
    default=None,
    help="Path to config.toml (default: platform data dir).",
)
@click.pass_context
def auth_test(ctx: click.Context, config_path: str | None) -> None:
    """Verify Reddit OAuth credentials. Exits 0 on success, 1 on failure."""
    builder: ClientBuilder = (
        ctx.obj.get("client_builder", build_client)
        if isinstance(ctx.obj, dict)
        else build_client
    )
    file_path = Path(config_path) if config_path else _default_config_file()
    try:
        config = cfg.load_config(env=os.environ, cli_overrides={}, file_path=file_path)
    except cfg.ConfigError as exc:
        click.echo(f"Config error: {exc}", err=True)
        ctx.exit(1)
        return

    try:
        client = builder(config)
        user = client.user.me()
    except Exception as exc:  # noqa: BLE001 - boundary; we collapse to a friendly message
        click.echo(
            f"auth test failed: {exc}\nRefresh token rejected? See README §Re-authenticating.",
            err=True,
        )
        ctx.exit(1)
        return

    name = getattr(user, "name", None) or "<unknown>"
    click.echo(f"OK — authenticated as u/{name}")


def _default_config_file() -> Path:
    return cfg.default_data_dir() / "config.toml"
