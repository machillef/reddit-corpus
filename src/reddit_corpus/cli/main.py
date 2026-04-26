"""Top-level click app for `reddit-corpus`.

Slice 5 wires up only the `auth` group. Other groups land in later slices.
"""

from __future__ import annotations

import click

from reddit_corpus.cli.auth_cmd import auth_group


@click.group()
@click.version_option(package_name="reddit-corpus")
def cli() -> None:
    """Personal Reddit corpus tool — ingest into SQLite, query for LLMs."""


cli.add_command(auth_group, name="auth")
