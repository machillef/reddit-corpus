"""PRAW client factory + subreddit canonicalization."""

from __future__ import annotations

import re

import praw

from reddit_corpus.config import Config

_URL_PREFIX_RE = re.compile(r"^https?://(?:www\.)?reddit\.com/?", flags=re.IGNORECASE)
_R_PREFIX_RE = re.compile(r"^r/", flags=re.IGNORECASE)


def build_client(config: Config) -> praw.Reddit:
    """Construct a praw.Reddit instance with refresh-token auth from Config."""
    return praw.Reddit(
        client_id=config.reddit.client_id,
        client_secret=config.reddit.client_secret,
        refresh_token=config.reddit.refresh_token,
        user_agent=config.reddit.user_agent,
    )


def canonicalize_subreddit(name: str) -> str:
    """Strip URL / `/r/` prefix forms and lowercase.

    Only strips an `r/` prefix when actually present — a bare name like `"rpg"`
    is preserved (the previous regex over-stripped its leading `r`).
    """
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("Subreddit name is empty.")
    cleaned = _URL_PREFIX_RE.sub("", cleaned)
    cleaned = cleaned.lstrip("/")
    cleaned = _R_PREFIX_RE.sub("", cleaned)
    cleaned = cleaned.strip("/").lower()
    if not cleaned:
        raise ValueError(f"Subreddit name is empty after canonicalization: {name!r}")
    return cleaned
