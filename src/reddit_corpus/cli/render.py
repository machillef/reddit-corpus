"""Output renderers for the read-side CLI commands.

Two formats per shape:
  - JSON: deterministic, mirrors the schema, easy to pipe through `jq`.
  - Markdown: compact, shaped for an LLM consumer (Claude Code) to read directly
    without spending tokens on field-name boilerplate. Default for humans.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone

from reddit_corpus.corpus.subreddits import SubredditRow
from reddit_corpus.reddit import Comment, Post

_REMOVAL_LABELS = {
    "present": "",
    "deleted_by_author": "*[deleted by author]*",
    "removed_by_mod": "*[removed by mod]*",
    "removed_other": "*[removed]*",
}


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


# ---------- markdown ---------- #


def _ts(epoch: int | None) -> str:
    if epoch is None:
        return "—"
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _author(name: str | None) -> str:
    return f"u/{name}" if name else "*[deleted]*"


def _removal_suffix(status: str) -> str:
    label = _REMOVAL_LABELS.get(status, "")
    return f" {label}" if label else ""


def _post_header(post: Post) -> str:
    author = _author(post.author)
    return (
        f"# r/{post.subreddit} — {post.title}\n"
        f"**{author}** • ▲{post.score} • {post.num_comments} comments • "
        f"{_ts(post.created_utc)}{_removal_suffix(post.removal_status)}"
    )


def render_posts_md(posts: Iterable[Post]) -> str:
    posts_list = list(posts)
    if not posts_list:
        return "*(no posts match these filters)*"
    out = []
    for p in posts_list:
        author = _author(p.author)
        out.append(
            f"- **{p.title}** ({p.id}) — {author} • ▲{p.score} • "
            f"{p.num_comments} comments • {_ts(p.created_utc)}"
            f"{_removal_suffix(p.removal_status)}"
        )
    return "\n".join(out)


def render_post_md(post: Post) -> str:
    body = post.selftext.strip() if post.selftext else ""
    sections = [_post_header(post)]
    if body:
        sections.append(body)
    if post.url and not post.is_self:
        sections.append(f"Link: <{post.url}>")
    if post.crosspost_parent_id:
        sections.append(f"*Crossposted from post id {post.crosspost_parent_id}*")
    return "\n\n".join(sections)


def render_thread_md(post: Post, comments: Sequence[Comment]) -> str:
    sections = [render_post_md(post)]
    if comments:
        sections.append(f"## Comments ({len(comments)})")
        for c in comments:
            indent = "  " * c.depth
            author = _author(c.author)
            tag = " *(reply)*" if c.depth > 0 else ""
            body = (c.body or "").strip().replace("\n", "\n" + indent + "  ")
            sections.append(
                f"{indent}### {author} ▲{c.score} • {_ts(c.created_utc)}"
                f"{tag}{_removal_suffix(c.removal_status)}\n"
                f"{indent}  {body}"
            )
    else:
        sections.append("## Comments (0)\n*(no comments yet)*")
    return "\n\n".join(sections)


def render_comments_md(comments: Iterable[Comment]) -> str:
    items = list(comments)
    if not items:
        return "*(no matches)*"
    out = []
    for c in items:
        author = _author(c.author)
        body = (c.body or "").strip().replace("\n", " ")
        out.append(
            f"- **{c.id}** in post `{c.post_id}` — {author} ▲{c.score} • "
            f"{_ts(c.created_utc)}{_removal_suffix(c.removal_status)}\n"
            f"  > {body}"
        )
    return "\n".join(out)


def render_subs_md(rows: Iterable[SubredditRow]) -> str:
    items = list(rows)
    if not items:
        return "*(no subreddits in corpus yet)*"
    out = ["| Subreddit | First seen | Last ingested |", "|---|---|---|"]
    for r in items:
        out.append(
            f"| r/{r.display_name} (`{r.name}`) | {_ts(r.first_seen_at)} | "
            f"{_ts(r.last_ingested_at)} |"
        )
    return "\n".join(out)
