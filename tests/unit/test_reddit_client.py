"""Tests for reddit.client.build_client.

The factory must construct a praw.Reddit with the right kwargs from a Config.
We monkeypatch the praw.Reddit symbol to record what we'd pass in.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from reddit_corpus import config as cfg
from reddit_corpus.reddit import client as reddit_client


@pytest.fixture
def sample_config(tmp_path: Path) -> cfg.Config:
    return cfg.Config(
        reddit=cfg.RedditAuth(
            client_id="cid",
            client_secret="csec",
            refresh_token="rtok",
            user_agent="ua/1.0",
        ),
        ingest=cfg.IngestSettings(),
        paths=cfg.Paths(db_path=tmp_path / "corpus.db"),
    )


def test_build_client_passes_credentials_to_praw(
    monkeypatch: pytest.MonkeyPatch, sample_config: cfg.Config
):
    captured: dict[str, Any] = {}

    class _StubReddit:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(reddit_client.praw, "Reddit", _StubReddit)

    client = reddit_client.build_client(sample_config)
    assert isinstance(client, _StubReddit)
    assert captured["client_id"] == "cid"
    assert captured["client_secret"] == "csec"
    assert captured["refresh_token"] == "rtok"
    assert captured["user_agent"] == "ua/1.0"


def test_canonicalize_subreddit_strips_prefixes_and_lowercases():
    cases = {
        "anthropic": "anthropic",
        "Anthropic": "anthropic",
        "r/Anthropic": "anthropic",
        "/r/Anthropic": "anthropic",
        "https://www.reddit.com/r/Anthropic": "anthropic",
        "https://reddit.com/r/Anthropic/": "anthropic",
        "  AskHistorians  ": "askhistorians",
    }
    for raw, expected in cases.items():
        assert reddit_client.canonicalize_subreddit(raw) == expected, raw


def test_canonicalize_subreddit_preserves_bare_name_starting_with_r():
    """A bare name like 'rpg' must NOT have its leading 'r' stripped — only 'r/' prefixes do."""
    assert reddit_client.canonicalize_subreddit("rpg") == "rpg"
    assert reddit_client.canonicalize_subreddit("RPG") == "rpg"
    assert reddit_client.canonicalize_subreddit("r/rpg") == "rpg"


def test_canonicalize_subreddit_rejects_empty():
    with pytest.raises(ValueError):
        reddit_client.canonicalize_subreddit("")
    with pytest.raises(ValueError):
        reddit_client.canonicalize_subreddit("   ")
