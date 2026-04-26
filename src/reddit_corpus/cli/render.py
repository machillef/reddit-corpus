"""Output renderers for the read-side CLI commands.

Slice 8 ships JSON only — deterministic shape mirroring the schema, easy to
assert on in tests and to pipe to `jq`. Slice 9 adds markdown variants.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Iterable, Sequence

from reddit_corpus.corpus.subreddits import SubredditRow
from reddit_corpus.reddit import Comment, Post


def post_to_dict(post: Post) -> dict[str, object]:
    return dataclasses.asdict(post)


def comment_to_dict(comment: Comment) -> dict[str, object]:
    return dataclasses.asdict(comment)


def render_posts_json(posts: Iterable[Post]) -> str:
    payload = {"posts": [post_to_dict(p) for p in posts]}
    return json.dumps(payload, indent=2, sort_keys=True)


def render_post_json(post: Post) -> str:
    return json.dumps({"post": post_to_dict(post)}, indent=2, sort_keys=True)


def render_thread_json(post: Post, comments: Sequence[Comment]) -> str:
    payload = {
        "post": post_to_dict(post),
        "comments": [comment_to_dict(c) for c in comments],
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def render_comments_json(comments: Iterable[Comment]) -> str:
    payload = {"comments": [comment_to_dict(c) for c in comments]}
    return json.dumps(payload, indent=2, sort_keys=True)


def render_subs_json(rows: Iterable[SubredditRow]) -> str:
    payload = {
        "subreddits": [
            {
                "name": r.name,
                "display_name": r.display_name,
                "first_seen_at": r.first_seen_at,
                "last_ingested_at": r.last_ingested_at,
            }
            for r in rows
        ]
    }
    return json.dumps(payload, indent=2, sort_keys=True)
