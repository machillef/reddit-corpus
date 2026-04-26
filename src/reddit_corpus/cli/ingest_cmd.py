"""`reddit-corpus ingest` and `reddit-corpus init`.

Both are flat (non-grouped) top-level commands per the design doc — they're
system-level operations on the corpus as a whole.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import click

from reddit_corpus import config as cfg
from reddit_corpus.corpus import comments as comments_dao
from reddit_corpus.corpus import posts as posts_dao
from reddit_corpus.corpus import schema
from reddit_corpus.corpus import subreddits as subs_dao
from reddit_corpus.reddit import ingest, ratelimit
from reddit_corpus.reddit.client import build_client, canonicalize_subreddit

ClientBuilder = Callable[[cfg.Config], Any]

log = logging.getLogger(__name__)

# When PRAW reports the per-account budget has dropped below this, we abort
# the next sub rather than risking a 429 mid-run.
_RATELIMIT_THRESHOLD = 10


def _open_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    schema.apply_schema(conn)
    return conn


def _resolve_overrides(
    config: cfg.Config, sub_arg: str | None, listings_arg: str | None
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if sub_arg:
        subs = tuple(canonicalize_subreddit(s) for s in sub_arg.split(",") if s.strip())
    else:
        subs = tuple(canonicalize_subreddit(s) for s in config.ingest.subreddits)
    if listings_arg:
        listings = tuple(s.strip() for s in listings_arg.split(",") if s.strip())
    else:
        listings = config.ingest.listings
    return subs, listings


def _default_config_file() -> Path:
    return cfg.default_data_dir() / "config.toml"


@click.command("ingest")
@click.option(
    "--config-path", type=click.Path(dir_okay=False, path_type=str), default=None
)
@click.option(
    "--sub",
    "sub_arg",
    default=None,
    help="Comma-separated subreddits, overrides config.",
)
@click.option(
    "--listings",
    "listings_arg",
    default=None,
    help="Comma-separated listing specs (new / hot / top[:WINDOW]), overrides config.",
)
@click.option(
    "--more-expand-limit",
    "more_expand_limit",
    type=int,
    default=None,
    help="Max MoreComments stubs to expand per post. Overrides config.",
)
@click.option("--dry-run", is_flag=True, help="Fetch but do not write to the DB.")
@click.pass_context
def ingest_cmd(
    ctx: click.Context,
    config_path: str | None,
    sub_arg: str | None,
    listings_arg: str | None,
    more_expand_limit: int | None,
    dry_run: bool,
) -> None:
    """Ingest configured subreddits into the local SQLite corpus."""
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

    subs, listings = _resolve_overrides(config, sub_arg, listings_arg)
    if not subs:
        click.echo(
            "No subreddits to ingest. Set [ingest].subreddits in config.toml or pass --sub.",
            err=True,
        )
        ctx.exit(1)
        return

    expand_limit = (
        more_expand_limit
        if more_expand_limit is not None
        else config.ingest.more_expand_limit
    )

    client = builder(config)
    conn = _open_db(config.paths.db_path)
    try:
        for sub in subs:
            stats = _ingest_one_sub(
                conn,
                client=client,
                sub=sub,
                listings=listings,
                more_expand_limit=expand_limit,
                dry_run=dry_run,
            )
            click.echo(
                f"r/{sub}: {stats['posts']} posts, {stats['comments']} comments, "
                f"{stats['failures']} failures"
            )
            state = ratelimit.observe(client)
            if ratelimit.should_pause(state, threshold=_RATELIMIT_THRESHOLD):
                click.echo(
                    f"Rate-limit budget low (remaining={state.remaining}). "
                    "Aborting remaining subs; rerun later.",
                    err=True,
                )
                break
    finally:
        conn.commit()
        conn.close()


def _ingest_one_sub(
    conn: sqlite3.Connection,
    *,
    client: Any,
    sub: str,
    listings: tuple[str, ...],
    more_expand_limit: int,
    dry_run: bool,
) -> dict[str, int]:
    now = int(time.time())
    n_posts = 0
    n_comments = 0
    n_failures = 0

    # Resolve the human-friendly display_name once via the client's Subreddit
    # object (PRAW caches this; one attribute read per ingest, not per post).
    display_name = _resolve_display_name(client, sub)

    if not dry_run:
        with conn:
            subs_dao.ensure_subreddit_row(
                conn, name=sub, display_name=display_name, first_seen_at=now
            )

    for listing_spec in listings:
        for submission in ingest.iter_submissions(client, sub, listing_spec):
            try:
                post, post_comments = ingest.expand_thread(
                    submission,
                    sub_canonical=sub,
                    fetched_at=now,
                    more_expand_limit=more_expand_limit,
                )
                if dry_run:
                    n_posts += 1
                    n_comments += len(post_comments)
                    continue

                with conn:
                    posts_dao.upsert_post(conn, post)
                    comments_dao.upsert_comments(conn, post_comments)
                n_posts += 1
                n_comments += len(post_comments)
            except Exception as exc:  # noqa: BLE001 - per-post isolation
                n_failures += 1
                log.warning("ingest failure on post %s: %s", _safe_id(submission), exc)
                # Fall through to next submission

    if not dry_run:
        with conn:
            subs_dao.touch_last_ingested(conn, name=sub, ts=now)

    return {"posts": n_posts, "comments": n_comments, "failures": n_failures}


def _resolve_display_name(client: Any, sub: str) -> str:
    """Return PRAW's preferred-casing display_name for a sub, or the canonical
    name if PRAW doesn't expose one."""
    try:
        return str(client.subreddit(sub).display_name) or sub
    except Exception:  # noqa: BLE001
        return sub


def _safe_id(submission: Any) -> str:
    try:
        return str(getattr(submission, "id", "<unknown>"))
    except Exception:  # noqa: BLE001
        return "<unknown>"


@click.command("init")
@click.option(
    "--config-path", type=click.Path(dir_okay=False, path_type=str), default=None
)
@click.pass_context
def init_cmd(ctx: click.Context, config_path: str | None) -> None:
    """Create the local SQLite database and apply the schema. Idempotent."""
    file_path = Path(config_path) if config_path else _default_config_file()
    try:
        config = cfg.load_config(env=os.environ, cli_overrides={}, file_path=file_path)
    except cfg.ConfigError as exc:
        click.echo(f"Config error: {exc}", err=True)
        ctx.exit(1)
        return

    db_path = config.paths.db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        schema.apply_schema(conn)
    finally:
        conn.close()
    click.echo(f"OK — schema applied to {db_path}")
    sys.stdout.flush()
