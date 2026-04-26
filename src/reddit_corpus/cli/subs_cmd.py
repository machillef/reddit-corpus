"""`reddit-corpus subs list`."""

from __future__ import annotations

import click

from reddit_corpus.cli import render
from reddit_corpus.cli._common import load_config_or_exit, open_db_or_exit
from reddit_corpus.corpus import subreddits as subs_dao


@click.group()
def subs_group() -> None:
    """Subreddit admin queries."""


@subs_group.command("list")
@click.option(
    "--config-path", type=click.Path(dir_okay=False, path_type=str), default=None
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["md", "json"]),
    default="md",
    show_default=True,
)
@click.pass_context
def subs_list(ctx: click.Context, config_path: str | None, fmt: str) -> None:
    """List subreddits in the corpus with first-seen and last-ingested timestamps."""
    config = load_config_or_exit(ctx, config_path)
    conn = open_db_or_exit(ctx, config.paths.db_path)
    try:
        rows = subs_dao.list_subreddits(conn)
        if fmt == "json":
            click.echo(render.render_subs_json(rows))
        else:
            click.echo(render.render_subs_md(rows))
    finally:
        conn.close()
