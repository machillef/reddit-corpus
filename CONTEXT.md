# reddit-corpus

A personal, longitudinal Reddit notebook: an ingester accumulates posts and comment trees from configured subreddits into a local SQLite store; a CLI surfaces structured queries shaped for LLM consumption.

## Language

**Notebook**:
The local SQLite database, considered as a curated, monotonically growing record of subreddit content shaped by *what the user and the LLM will ask* — not a faithful Reddit replica. Lossy decisions (collapsed flags, capped comment expansion) are features, not compromises.
_Avoid_: Mirror, archive, replica, dataset.

**Corpus**:
The user-facing name for the Notebook. Used in CLI commands, docs, and prose. The Notebook is the implementation; the Corpus is the concept. (Glossary entries below use whichever reads more naturally; they refer to the same thing.)
_Avoid_: Database, db, store, when speaking at the conceptual layer.

**Removal status**:
The visibility state of a Post or Comment, captured at fetch time as one of: `present`, `deleted_by_author`, `removed_by_mod`, `removed_other`. Deliberately NOT collapsed into a boolean — mod-removal vs author-deletion is an analytically useful signal under the Notebook stance. Renderers display each state distinctly in markdown output.
_Avoid_: "removed" as a boolean, "deleted" as a synonym for any removal.

**Parent-comment-id**:
The `comments.parent_comment_id` column. NULL means the Comment is a top-level reply directly on the Post (the Post relationship lives in the separate `post_id` column). Non-NULL means the parent is another Comment in the same table — enforced by FK to `comments(id)` with `ON DELETE CASCADE`. Comments are inserted in tree-walk order (parents first) so FK enforcement is satisfied row by row at ingest time.
_Avoid_: `parent_id` (ambiguous; doesn't say which entity it points at).

**Subreddit name** (canonical):
The lowercase, prefix-free identity of a subreddit. The `subreddits.name` column. Always canonicalized at the boundary (CLI input, config-file load): the canonicalizer strips `r/`, `/r/`, `https?://(www\.)?reddit\.com/r/`, leading/trailing slashes, and lowercases. Stored once per subreddit; serves as the primary key and FK target.
_Avoid_: "subreddit URL", "subreddit slug", "/r/whatever" as a stored form.

**Subreddit display name**:
The `subreddits.display_name` column. Reddit's preferred casing for the same subreddit (e.g., `Anthropic`, `AskHistorians`). Used by markdown renderers for human-friendly headers; never used for identity or lookup. Captured from PRAW's `Subreddit.display_name` on first encounter.
_Avoid_: using `display_name` for any equality check or DB lookup.

**Fetched-at**:
The `posts.fetched_at` / `comments.fetched_at` column — unix seconds, updated on **every encounter** (last successful row write). Doubles as a freshness oracle: stale `fetched_at` means "we haven't seen this row recently", which is the closest the Notebook gets to a "is this still on Reddit?" signal. We do NOT track disappearance with a separate column; vanished content stays as last seen.
_Avoid_: confusing this with `created_utc` (which is when Reddit says the content was created — immutable) or with `subreddits.last_ingested_at` (which is the per-sub run-level timestamp).

**Crosspost parent id**:
The `posts.crosspost_parent_id` column. NULL means the Post is original (or its crosspost lineage is unknown to PRAW). Non-NULL holds the Reddit id of the post this one was crossposted from. Soft pointer — NO foreign-key constraint, because the parent may be in a Subreddit we don't track. Used by markdown renderers to add a "crossposted from r/X" line and by future analytical queries that join the table on itself.
_Avoid_: treating this as a hard reference; treating crossposts as duplicates to deduplicate away.

**Subcommand group**:
A click `@click.group()` that namespaces commands by *resource* (`posts`, `thread`, `comments`, `subs`, `auth`). All read operations live under a group. Top-level commands (`ingest`, `init`) are reserved for *system-level* operations on the corpus as a whole. Pattern follows `kubectl` / `gh` / `git` / `cargo` — chosen for hallucination resistance in LLM-driven invocation. We do NOT alias commands across groups (no `show-post --with-comments` shortcut for `thread show`); two-ways-to-do-one-thing is a hallucination magnet.
_Avoid_: flat verb-noun naming for read commands (`list-posts`, `show-post`); cross-group aliases.

**Post** / **Comment** (canonical types):
Plain Python dataclasses defined in `reddit_corpus.reddit`. The single canonical type per concept, used at every layer above `reddit/client.py` — `reddit/` produces them from PRAW Submissions/Comments; `corpus/` consumes them on write and *returns* them on read (constructed from `sqlite3.Row` at the boundary); `cli/render.py` consumes them. PRAW's `praw.models.Submission` and `praw.models.Comment` are confined to `reddit/client.py` and `reddit/ingest.py` and NEVER imported above the `reddit/` boundary (avoids name shadowing).
_Avoid_: `PostPayload` / `CommentPayload` (the "Payload" suffix implied a wire-vs-row distinction that doesn't exist in this notebook); `Submission` (PRAW's term — used only inside `reddit/`).

## Relationships

- The **Corpus** is one **Notebook** — single file per machine.
- A **Notebook** holds many **Subreddits**, each holding many **Posts**, each holding zero or more **Comments**. (These are placeholder terms — they get sharper definitions as we resolve more questions.)

## Example dialogue

> **Dev:** "Should we preserve crossposts as separate rows in each subreddit?"
> **Domain expert:** "We're a **Notebook**, not a **Mirror**. If the same content shows up in two subs and the LLM needs to see both, the LLM can ask. We don't pre-duplicate."

> **Dev:** "Reddit returns three different removal states. Worth distinguishing?"
> **Domain expert:** "Notebook stance says *if it's useful for analysis, keep it; if not, drop it.* Mod-removal vs author-deletion is analytically useful — keep it. Banned-author edge cases — collapse with mod-removal."

## Flagged ambiguities

_(none yet — this section grows as we resolve terms.)_
