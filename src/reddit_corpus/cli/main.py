"""Top-level click app for `reddit-corpus`."""

from __future__ import annotations

import click

from reddit_corpus.cli.auth_cmd import auth_group
from reddit_corpus.cli.comments_cmd import comments_group
from reddit_corpus.cli.ingest_cmd import ingest_cmd, init_cmd
from reddit_corpus.cli.posts_cmd import posts_group
from reddit_corpus.cli.subs_cmd import subs_group
from reddit_corpus.cli.thread_cmd import thread_group


@click.group()
@click.version_option(package_name="reddit-corpus")
def cli() -> None:
    """Personal Reddit corpus tool — ingest into SQLite, query for LLMs."""


cli.add_command(auth_group, name="auth")
cli.add_command(comments_group, name="comments")
cli.add_command(ingest_cmd)
cli.add_command(init_cmd)
cli.add_command(posts_group, name="posts")
cli.add_command(subs_group, name="subs")
cli.add_command(thread_group, name="thread")
