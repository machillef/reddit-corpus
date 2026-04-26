"""Tests for reddit.ingest.pull_listing and the listing-spec parser."""

from __future__ import annotations

import pytest

from reddit_corpus.reddit import ingest
from tests.fakes.praw_fakes import (
    FakeAuthorRef,
    FakeSubmission,
    make_fake_reddit_with,
)


def _sub(id: str, **kw) -> FakeSubmission:
    return FakeSubmission(
        id=id,
        title=kw.get("title", f"title-{id}"),
        selftext=kw.get("selftext", ""),
        url=kw.get("url"),
        score=kw.get("score", 1),
        num_comments=kw.get("num_comments", 0),
        link_flair_text=kw.get("flair"),
        created_utc=kw.get("created_utc", 1_700_000_000),
        is_self=kw.get("is_self", True),
        locked=kw.get("locked", False),
        author=kw.get("author", FakeAuthorRef("alice")),
        removed_by_category=kw.get("removed_by_category"),
        crosspost_parent=kw.get("crosspost_parent"),
    )


def test_parse_listing_spec_new():
    sort, time_filter = ingest.parse_listing_spec("new")
    assert sort == "new"
    assert time_filter is None


def test_parse_listing_spec_hot():
    sort, time_filter = ingest.parse_listing_spec("hot")
    assert sort == "hot"
    assert time_filter is None


@pytest.mark.parametrize("window", ["hour", "day", "week", "month", "year", "all"])
def test_parse_listing_spec_top_with_window(window: str):
    sort, time_filter = ingest.parse_listing_spec(f"top:{window}")
    assert sort == "top"
    assert time_filter == window


def test_parse_listing_spec_top_without_window_defaults_to_all():
    sort, time_filter = ingest.parse_listing_spec("top")
    assert sort == "top"
    assert time_filter == "all"


def test_parse_listing_spec_invalid_raises():
    with pytest.raises(ValueError):
        ingest.parse_listing_spec("rising")
    with pytest.raises(ValueError):
        ingest.parse_listing_spec("top:century")


def test_pull_listing_yields_post_dataclasses():
    client = make_fake_reddit_with(
        "anthropic",
        [
            _sub("p1", title="Hello", score=10, num_comments=2),
            _sub("p2", title="World", score=5),
        ],
        display_name="Anthropic",
    )
    posts = list(ingest.pull_listing(client, "anthropic", "new", fetched_at=1234))
    assert [p.id for p in posts] == ["p1", "p2"]
    assert posts[0].title == "Hello"
    assert posts[0].subreddit == "anthropic"
    assert posts[0].fetched_at == 1234
    assert posts[0].removal_status == "present"
    assert posts[0].author == "alice"


def test_pull_listing_canonicalizes_subreddit_input():
    client = make_fake_reddit_with("anthropic", [_sub("p1")])
    # "/r/Anthropic" should be canonicalized to "anthropic" before lookup.
    posts = list(ingest.pull_listing(client, "/r/Anthropic", "new", fetched_at=1))
    assert [p.id for p in posts] == ["p1"]
    assert posts[0].subreddit == "anthropic"


def test_pull_listing_maps_removed_categories_to_status():
    cases = [
        (None, "present"),
        ("deleted", "deleted_by_author"),
        ("moderator", "removed_by_mod"),
        ("automod_filtered", "removed_other"),
    ]
    for raw, expected in cases:
        client = make_fake_reddit_with(
            "anthropic", [_sub("p1", removed_by_category=raw)]
        )
        posts = list(ingest.pull_listing(client, "anthropic", "new", fetched_at=1))
        assert posts[0].removal_status == expected, raw


def test_pull_listing_maps_null_author_to_none():
    client = make_fake_reddit_with("anthropic", [_sub("p1", author=None)])
    posts = list(ingest.pull_listing(client, "anthropic", "new", fetched_at=1))
    assert posts[0].author is None


def test_pull_listing_extracts_crosspost_parent_id():
    """PRAW exposes crosspost_parent as a 't3_xxxxx' fullname; we strip the prefix."""
    client = make_fake_reddit_with(
        "anthropic", [_sub("p1", crosspost_parent="t3_origpost")]
    )
    posts = list(ingest.pull_listing(client, "anthropic", "new", fetched_at=1))
    assert posts[0].crosspost_parent_id == "origpost"


def test_pull_listing_supports_top_window():
    client = make_fake_reddit_with("anthropic", [_sub("p1"), _sub("p2")])
    posts = list(ingest.pull_listing(client, "anthropic", "top:week", fetched_at=1))
    assert {p.id for p in posts} == {"p1", "p2"}


def test_pull_listing_invalid_spec_raises():
    client = make_fake_reddit_with("anthropic", [_sub("p1")])
    with pytest.raises(ValueError):
        list(ingest.pull_listing(client, "anthropic", "rising", fetched_at=1))
