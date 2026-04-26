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

**Listing spec**:
A string of the form `new`, `hot`, or `top:WINDOW` (WINDOW ∈ {`hour`, `day`, `week`, `month`, `year`, `all`}) used in `[ingest].listings` and the `--listings` CLI flag to choose what kind of feed to ingest from a Subreddit. Parsed by `reddit_corpus.reddit.ingest.parse_listing_spec` into `(sort, time_filter)`.
_Avoid_: "listing type", "sort", "feed" (each is wider or narrower than what we mean here).

**Comment forest**:
The PRAW-shaped structure of all top-level Comments on a Post plus their nested replies, before flattening. Mirrors `praw.models.CommentForest`. The ingest pipeline walks the forest depth-first, parents before children, after `replace_more()` drops `MoreComments` stubs.
_Avoid_: "comment list" (a forest has structure, a list does not), "comment thread" when meaning the structure rather than the rendered output.

**Tree-walk order**:
The flat ordering of Comments where every Comment appears strictly after its parent, with siblings ordered by `created_utc` ascending. Load-bearing contract: a sequential `upsert_comments` pass on a tree-walked list satisfies the FK on `parent_comment_id` row by row at insert time.
_Avoid_: "depth-first" (descriptive but ambiguous about sibling order), "BFS", "tree order".

**More-expand limit**:
The `limit` argument to PRAW's `submission.comments.replace_more(limit=N)`. Caps the number of `MoreComments` stubs expanded per Post — *not* a tree-depth cap. Default 32; 0 disables expansion entirely. Configurable via `[ingest].more_expand_limit` and the `--more-expand-limit` CLI flag on `ingest`. Stubs we don't expand are dropped from the local Comment forest, not written to the Notebook.
_Avoid_: "comment limit", "depth limit", "expansion budget".

**Orphan Comment**:
A Comment whose `parent_comment_id` refers to another Comment that is not present in the local Comment forest, typically because the parent was a `MoreComments` stub we didn't expand or because Reddit has admin-deleted the parent between fetches. The Notebook keeps these and emits them at the tail of `walk_thread` with `parent_comment_id` rewritten to `NULL` and `depth = 0`, rather than dropping them.
_Avoid_: "dangling comment", "broken comment".

**Drift policy**:
The rule for what happens when the ingester re-encounters Post or Comment content. v1's policy is `overwrite` — the latest fetch wins, edits and score history are silently lost, no snapshot tables are kept. Implemented via `INSERT … ON CONFLICT(id) DO UPDATE` so re-encountering a Post does not cascade-delete its Comments. Considered alternatives at design time: `snapshot-on-fetch` (rejected for storage cost) and `hybrid` (rejected for query complexity).
_Avoid_: "history policy", "change tracking", "snapshot policy" — those imply we keep history; we deliberately don't.

## Reddit auth

**Data API**:
Reddit's official, OAuth-protected HTTP API, accessed via PRAW. The only network surface this project uses. Subject to Reddit's [Responsible Builder Policy](https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy).
_Avoid_: "Reddit API" without qualifier (Reddit also exposes an Ads API and a Devvit Platform API; the unqualified term is ambiguous), "official API".

**Devvit**:
Reddit's *in-Reddit* application platform — apps that run on Reddit's serverless infrastructure and render inside Reddit's UI for subreddits the developer moderates. Not a fit for this project: Devvit cannot write to a user's local disk or run on a host-side scheduler, both of which the corpus depends on. See `docs/adr/0002-reddit-api-pre-approval.md` for the architectural mismatch.
_Avoid_: "Reddit Apps", "Reddit Platform" — these are marketing-level umbrellas that include Devvit plus other surfaces.

**Responsible Builder Policy** (RBP):
Reddit's late-2025 policy that gates new Data API credentials behind manual review via the Developer Support form. The reason `reddit.com/prefs/apps` silently fails for new accounts: the page submits, the backend rejects, and the UI bounces back to the captcha. See ADR 0002.
_Avoid_: "the new API rules" — too vague; spell it out.

**Script app**:
The Reddit app type that authenticates as the developer's own account only (not on behalf of other users). Registered at `reddit.com/prefs/apps` with `redirect_uri = http://localhost:8080`. The only app type this project supports.
_Avoid_: "personal app", "OAuth app" — both are ambiguous (Reddit has three OAuth app types).

**Refresh token**:
The long-lived OAuth credential obtained once via the bootstrap dance documented in README §Setup step 3, stored in `config.toml` under `[reddit].refresh_token`, and exchanged by PRAW for short-lived access tokens on every request. **Account-scoped, not host-scoped** — once you have one, copy the same value across every PC that needs it.
_Avoid_: "auth token", "OAuth token" — these are ambiguous between the long-lived refresh and the short-lived access token. The project never handles the access token directly.

**Reddit credentials**:
The 4-tuple `(client_id, client_secret, refresh_token, user_agent)` that the ingester needs to make authenticated calls. All four live together in `[reddit]` in `config.toml` or in `REDDIT_CORPUS_*` environment variables. When precision matters, name the specific field; "Reddit credentials" is the shorthand for the full set.
_Avoid_: using "Reddit credentials" to mean only `(client_id, client_secret)` or only the **Refresh token** — be specific.

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
