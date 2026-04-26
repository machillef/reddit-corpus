"""Tests for reddit.ingest.expand_thread."""

from __future__ import annotations

import pytest

from reddit_corpus.reddit import ingest
from tests.fakes.praw_fakes import (
    FakeAuthorRef,
    FakeComment,
    FakeCommentForest,
    FakeMoreComments,
    FakeSubmission,
)


def _comment(
    cid: str,
    parent_id: str,
    *,
    body: str = "body",
    author: str | None = "alice",
    score: int = 1,
    created_utc: float = 100.0,
    removed_by_category: str | None = None,
    replies: list[FakeComment] | None = None,
) -> FakeComment:
    return FakeComment(
        id=cid,
        body=body,
        score=score,
        created_utc=created_utc,
        parent_id=parent_id,
        author=FakeAuthorRef(author),
        removed_by_category=removed_by_category,
        replies=replies or [],
    )


def _submission_with_forest(post_id: str, top_level: list) -> FakeSubmission:
    return FakeSubmission(
        id=post_id,
        title="t",
        score=1,
        num_comments=sum(1 for _ in top_level),
        created_utc=10.0,
        comments=FakeCommentForest(top_level=top_level),
    )


def test_expand_thread_returns_post_and_flat_comments():
    sub = _submission_with_forest(
        "p1",
        [_comment("c1", "t3_p1", body="top reply")],
    )
    post, comments = ingest.expand_thread(
        sub, sub_canonical="anthropic", more_expand_limit=32, fetched_at=1234
    )
    assert post.id == "p1"
    assert post.subreddit == "anthropic"
    assert post.fetched_at == 1234
    assert len(comments) == 1
    c = comments[0]
    assert c.id == "c1"
    assert c.post_id == "p1"
    assert c.parent_comment_id is None  # top-level: parent is the post
    assert c.depth == 0
    assert c.body == "top reply"
    assert c.author == "alice"
    assert c.fetched_at == 1234


def test_expand_thread_assigns_depth_and_parent_for_nested():
    """Nested comments get depth=1, depth=2, ... and parent_comment_id pointing
    at the actual parent comment id (not the t1_ fullname)."""
    grandchild = _comment("c-gc", "t1_c-child", body="grandchild")
    child = _comment("c-child", "t1_c-root", body="child", replies=[grandchild])
    root = _comment("c-root", "t3_p1", body="root", replies=[child])
    sub = _submission_with_forest("p1", [root])
    _, comments = ingest.expand_thread(
        sub, sub_canonical="anthropic", more_expand_limit=32, fetched_at=1
    )
    by_id = {c.id: c for c in comments}
    assert by_id["c-root"].depth == 0
    assert by_id["c-root"].parent_comment_id is None
    assert by_id["c-child"].depth == 1
    assert by_id["c-child"].parent_comment_id == "c-root"
    assert by_id["c-gc"].depth == 2
    assert by_id["c-gc"].parent_comment_id == "c-child"


def test_expand_thread_emits_in_tree_walk_order():
    """Parents must appear before their children in the output list, so a
    sequential `upsert_comments` pass satisfies the parent_comment_id FK row by row."""
    a1a = _comment("a1a", "t1_a1")
    a1 = _comment("a1", "t1_a", replies=[a1a])
    a2 = _comment("a2", "t1_a")
    a = _comment("a", "t3_p1", replies=[a1, a2])
    b = _comment("b", "t3_p1")
    sub = _submission_with_forest("p1", [a, b])
    _, comments = ingest.expand_thread(
        sub, sub_canonical="anthropic", more_expand_limit=32, fetched_at=1
    )
    ids = [c.id for c in comments]
    assert ids.index("a") < ids.index("a1")
    assert ids.index("a1") < ids.index("a1a")
    assert ids.index("a") < ids.index("a2")
    assert ids.index("b") > ids.index("a")  # 'b' is a separate top-level


def test_expand_thread_calls_replace_more_with_limit():
    sub = _submission_with_forest("p1", [_comment("c1", "t3_p1")])
    ingest.expand_thread(
        sub, sub_canonical="anthropic", more_expand_limit=16, fetched_at=1
    )
    assert sub.comments.replace_more_called_with == [16]


def test_expand_thread_drops_more_stubs_after_replace_more():
    """A FakeMoreComments stub at the top level is dropped, not yielded as a Comment."""
    sub = _submission_with_forest(
        "p1",
        [_comment("c1", "t3_p1"), FakeMoreComments(id="more1")],
    )
    _, comments = ingest.expand_thread(
        sub, sub_canonical="anthropic", more_expand_limit=32, fetched_at=1
    )
    assert {c.id for c in comments} == {"c1"}


def test_expand_thread_maps_removed_categories():
    sub = _submission_with_forest(
        "p1",
        [
            _comment("c1", "t3_p1", removed_by_category="moderator"),
            _comment("c2", "t3_p1", removed_by_category="deleted"),
            _comment("c3", "t3_p1", removed_by_category=None),
        ],
    )
    _, comments = ingest.expand_thread(
        sub, sub_canonical="anthropic", more_expand_limit=32, fetched_at=1
    )
    by_id = {c.id: c for c in comments}
    assert by_id["c1"].removal_status == "removed_by_mod"
    assert by_id["c2"].removal_status == "deleted_by_author"
    assert by_id["c3"].removal_status == "present"


def test_expand_thread_handles_null_author():
    sub = _submission_with_forest("p1", [_comment("c1", "t3_p1", author=None)])
    _, comments = ingest.expand_thread(
        sub, sub_canonical="anthropic", more_expand_limit=32, fetched_at=1
    )
    assert comments[0].author is None


def test_expand_thread_default_more_expand_limit_is_32():
    """The plan says 32 is the default. Verify it propagates."""
    sub = _submission_with_forest("p1", [_comment("c1", "t3_p1")])
    ingest.expand_thread(sub, sub_canonical="anthropic", fetched_at=1)
    assert sub.comments.replace_more_called_with == [32]


def test_expand_thread_zero_limit_disables_expansion():
    """A limit of 0 means 'don't expand any MoreComments stubs'."""
    sub = _submission_with_forest(
        "p1",
        [_comment("c1", "t3_p1"), FakeMoreComments(id="more1")],
    )
    ingest.expand_thread(
        sub, sub_canonical="anthropic", more_expand_limit=0, fetched_at=1
    )
    assert sub.comments.replace_more_called_with == [0]


def test_expand_thread_handles_orphan_parent_id_gracefully():
    """If a comment's parent_id points at something we don't have (e.g. a
    MoreComments stub), it should still be emitted with parent_comment_id=None
    and depth=0 rather than crashing."""
    orphan = _comment("orphan", "t1_ghost", body="parent missing")
    sub = _submission_with_forest("p1", [orphan])
    _, comments = ingest.expand_thread(
        sub, sub_canonical="anthropic", more_expand_limit=32, fetched_at=1
    )
    assert len(comments) == 1
    assert comments[0].id == "orphan"


@pytest.mark.parametrize(
    "parent_id,expected_parent",
    [
        ("t3_p1", None),  # top-level (parent is the post)
        ("t1_c-something", "c-something"),  # nested under another comment
    ],
)
def test_parent_id_decoding(parent_id: str, expected_parent: str | None):
    """t3_xxx means parent is the post; t1_yyy means parent is comment yyy."""
    sub = _submission_with_forest("p1", [_comment("c1", parent_id)])
    # 'c-something' has to exist if we expect it to be the parent
    if expected_parent is not None:
        sub.comments.top_level = [
            _comment("c-something", "t3_p1", replies=[_comment("c1", parent_id)])
        ]
    _, comments = ingest.expand_thread(
        sub, sub_canonical="anthropic", more_expand_limit=32, fetched_at=1
    )
    by_id = {c.id: c for c in comments}
    assert "c1" in by_id
    assert by_id["c1"].parent_comment_id == expected_parent
