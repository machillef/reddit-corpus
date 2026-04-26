"""`reddit-corpus thread show` — post + full comment tree."""

from __future__ import annotations

import click

from reddit_corpus.cli import render
from reddit_corpus.cli._common import load_config_or_exit, open_db_or_exit
from reddit_corpus.corpus import comments as comments_dao
from reddit_corpus.corpus import posts as posts_dao


@click.group()
def thread_group() -> None:
    """Thread-shaped queries (post + comment tree)."""


@thread_group.command("show")
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
def thread_show(
    ctx: click.Context,
    post_id: str,
    config_path: str | None,
    fmt: str,
) -> None:
    """Fetch a post and its full comment tree in tree-walk order."""
    config = load_config_or_exit(ctx, config_path)
    conn = open_db_or_exit(ctx, config.paths.db_path)
    try:
        post = posts_dao.get_post(conn, post_id)
        if post is None:
            click.echo(f"No post with id {post_id!r} in the corpus.", err=True)
            ctx.exit(1)
            return
        thread = comments_dao.walk_thread(conn, post_id)
        if fmt == "json":
            click.echo(render.render_thread_json(post, thread))
        else:
            click.echo(render.render_thread_md(post, thread))
    finally:
        conn.close()
