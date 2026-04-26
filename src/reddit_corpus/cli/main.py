"""Top-level click app for `reddit-corpus`."""

from __future__ import annotations

import click

from reddit_corpus.cli.auth_cmd import auth_group
from reddit_corpus.cli.ingest_cmd import ingest_cmd, init_cmd


@click.group()
@click.version_option(package_name="reddit-corpus")
def cli() -> None:
    """Personal Reddit corpus tool — ingest into SQLite, query for LLMs."""


cli.add_command(auth_group, name="auth")
cli.add_command(ingest_cmd)
cli.add_command(init_cmd)
