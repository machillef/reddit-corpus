"""`reddit-corpus comments search` — regex search over comment bodies."""

from __future__ import annotations

import sqlite3

import click

from reddit_corpus.cli import render
from reddit_corpus.cli._common import load_config_or_exit, open_db_or_exit
from reddit_corpus.corpus import comments as comments_dao
from reddit_corpus.reddit.client import canonicalize_subreddit


@click.group()
def comments_group() -> None:
    """Comment-level queries."""


@comments_group.command("search")
@click.option(
    "--config-path", type=click.Path(dir_okay=False, path_type=str), default=None
)
@click.option("--sub", required=True, help="Subreddit to scope the search to.")
@click.option("--pattern", required=True, help="Python regex (re.search semantics).")
@click.option("--limit", type=int, default=50, show_default=True)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["md", "json"]),
    default="md",
    show_default=True,
)
@click.pass_context
def comments_search(
    ctx: click.Context,
    config_path: str | None,
    sub: str,
    pattern: str,
    limit: int,
    fmt: str,
) -> None:
    """Search comment bodies in `sub` for a regex pattern."""
    config = load_config_or_exit(ctx, config_path)
    conn = open_db_or_exit(ctx, config.paths.db_path)
    try:
        canonical = canonicalize_subreddit(sub)
        try:
            hits = comments_dao.search_comments(
                conn, sub=canonical, pattern=pattern, limit=limit
            )
        except sqlite3.OperationalError as exc:
            # `apply_schema`'s REGEXP shim now propagates `re.error` rather than
            # silently returning empty results — surface a friendly message.
            click.echo(f"Invalid regex pattern: {exc}", err=True)
            ctx.exit(2)
            return
        if fmt == "json":
            click.echo(render.render_comments_json(hits))
        else:
            click.echo(render.render_comments_md(hits))
    finally:
        conn.close()
