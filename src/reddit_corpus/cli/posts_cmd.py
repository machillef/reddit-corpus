"""`reddit-corpus posts list` and `posts show`."""

from __future__ import annotations

from typing import cast

import click

from reddit_corpus.cli import render
from reddit_corpus.cli._common import (
    load_config_or_exit,
    open_db_or_exit,
    parse_since,
)
from reddit_corpus.corpus import posts as posts_dao
from reddit_corpus.corpus.posts import SortKey
from reddit_corpus.reddit.client import canonicalize_subreddit


@click.group()
def posts_group() -> None:
    """Read-side post queries."""


@posts_group.command("list")
@click.option(
    "--config-path", type=click.Path(dir_okay=False, path_type=str), default=None
)
@click.option(
    "--sub", required=True, help="Subreddit name (canonical or with r/ prefix)."
)
@click.option(
    "--since", "since_arg", default=None, help="Relative (7d, 24h, 2w) or ISO date."
)
@click.option("--top", "top_n", type=int, default=None, help="Cap results to N posts.")
@click.option(
    "--sort",
    type=click.Choice(["score", "created"]),
    default="score",
    show_default=True,
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["md", "json"]),
    default="md",
    show_default=True,
    help="Output format.",
)
@click.pass_context
def posts_list(
    ctx: click.Context,
    config_path: str | None,
    sub: str,
    since_arg: str | None,
    top_n: int | None,
    sort: str,
    fmt: str,
) -> None:
    """List posts in a subreddit, filtered by recency, sorted by score or created."""
    config = load_config_or_exit(ctx, config_path)
    conn = open_db_or_exit(ctx, config.paths.db_path)
    try:
        canonical = canonicalize_subreddit(sub)
        since = parse_since(since_arg)
        # `click.Choice(["score", "created"])` already constrains `sort`; cast
        # to satisfy the Literal type signature on `list_posts`.
        rows = posts_dao.list_posts(
            conn,
            sub=canonical,
            since=since,
            top_n=top_n,
            sort=cast(SortKey, sort),
        )
        if fmt == "json":
            click.echo(render.render_posts_json(rows))
        else:
            click.echo(render.render_posts_md(rows))
    finally:
        conn.close()


@posts_group.command("show")
@click.argument("post_id")
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
def posts_show(
    ctx: click.Context,
    post_id: str,
    config_path: str | None,
    fmt: str,
) -> None:
    """Fetch a single post by id (no comments — use `thread show` for that)."""
    config = load_config_or_exit(ctx, config_path)
    conn = open_db_or_exit(ctx, config.paths.db_path)
    try:
        post = posts_dao.get_post(conn, post_id)
        if post is None:
            click.echo(f"No post with id {post_id!r} in the corpus.", err=True)
            ctx.exit(1)
            return
        if fmt == "json":
            click.echo(render.render_post_json(post))
        else:
            click.echo(render.render_post_md(post))
    finally:
        conn.close()
