# Design: reddit-scraper

> Approved: 2026-04-26. This document captures the architecture agreed in brainstorming. Implementation details (exact file contents, test names) are deferred to slice plans.
>
> **Canonical terminology lives in `CONTEXT.md` at the repo root. Foundational rationale lives in `docs/adr/`.** Read `CONTEXT.md` before changing any name in this document; it is the source of truth for terms like Notebook, Corpus, Removal status, Subreddit name canonical, Subreddit display name, Fetched-at, Crosspost parent id, Subcommand group, Post / Comment, and Parent-comment-id.

## User stories

Numbered for traceability. Every story must be covered by at least one slice (`slices.md`).

| # | Role | Story |
|---|------|-------|
| 1 | User | Run `reddit-corpus ingest` on the configured subreddits and have new posts + their full comment trees written to local SQLite. |
| 2 | User | Override the configured subs and listings on a single run via CLI flags (`--sub`, `--listings`). |
| 3 | User | Configure subreddits, listings, OAuth credentials, and runtime knobs in a TOML file in the platform data dir. |
| 4 | LLM consumer (Claude Code / Codex) | List posts in a subreddit filtered by recency, with a sort order, in markdown or JSON. |
| 5 | LLM consumer | Fetch a single post + its full comment tree as either markdown or JSON. |
| 6 | LLM consumer | Search posts and/or comments by regex pattern within a subreddit. |
| 7 | LLM consumer | Choose `--format md` (default) or `--format json` on any read command. |
| 8 | User | Verify Reddit OAuth credentials work via `auth test` before scheduling a job. |
| 9 | User | List subreddits in the corpus with row counts and last-ingest timestamps. |
| 10 | User | Run a pre-flight check before installation that surfaces missing prerequisites with OS-specific install instructions. |
| 11 | Admin user | Create or re-create the local SQLite schema via `init`. |
| 12 | User | Run the entire tool unchanged on Windows, Linux, and macOS. |
| 13 | User | Trust that the ingester honors Reddit's API rate limits without manual configuration. |

---

## Overview

A personal Reddit corpus tool with two cooperating responsibilities, packaged as a single Python module with a single CLI binary `reddit-corpus`:

1. **Ingester** — pulls posts and full comment trees from configured subreddits via `praw`, writes them to a local SQLite database. Designed to run on a user-managed schedule (Task Scheduler / cron / launchd) on any of Windows / Linux / macOS.
2. **Analysis CLI** — exposes structured query subcommand groups (`posts list`, `posts show`, `thread show`, `comments search`, `subs list`, `auth test`) that return data formatted for LLM consumption (markdown by default, JSON behind a flag), so Claude Code or Codex can synthesize from the corpus without spending tokens on fetching.

Both share the same SQLite store and schema. The ingester writes; the CLI reads. Drift policy is **overwrite** — re-encountering a post or comment upserts the latest fetched state with no history. (See `requirements.md` "Drift policy" decision rationale.)

---

## Architecture

Three internal layers with one-way dependency: `cli → corpus → reddit`.

```
src/reddit_corpus/
├── reddit/                    # Network layer
│   ├── client.py              # PRAW factory, refresh-token auth
│   ├── ingest.py              # listing pull + comment expansion
│   └── ratelimit.py           # observation, threshold-based abort
├── corpus/                    # Storage layer (pure over a sqlite3.Connection)
│   ├── schema.py              # CREATE TABLE statements + version
│   ├── posts.py               # upsert_post, get_post, list_posts, ...
│   └── comments.py            # upsert_comments, walk_thread, search
├── cli/                       # Presentation layer (click subcommand groups)
│   ├── main.py                # entry point, top-level group, dispatch
│   ├── ingest_cmd.py          # top-level: ingest, init
│   ├── posts_cmd.py           # `posts list`, `posts show`
│   ├── thread_cmd.py          # `thread show`
│   ├── comments_cmd.py        # `comments search`
│   ├── subs_cmd.py            # `subs list`
│   ├── auth_cmd.py            # `auth test`
│   └── render.py              # markdown + json renderers (shared)
└── config.py                  # config + path resolution + secrets loading
```

**Why three layers:** `corpus/` never imports from `reddit/`. The CLI passes already-fetched payloads down. This means the storage layer is unit-testable with `:memory:` SQLite without ever invoking PRAW or hitting the network. Ditto the renderers — they take corpus rows and emit text, no deeper dependencies. The cost is roughly 50 lines of boilerplate over a flat module; it pays for itself by Slice 2.

**Files (not packages) for the leaf modules** until any one of them grows past ~200 lines, at which point split locally. Premature subpackages add navigation cost without earning their keep at this scale.

---

## Components

### `reddit_corpus.reddit`

- **`client.py`** — Builds a `praw.Reddit` instance from config. Refresh-token auth (script app registered at reddit.com/prefs/apps). Sets a descriptive `user_agent` per Reddit's API rules.
- **`ingest.py`** — Two functions:
  - `pull_listing(client, subreddit, listing_spec) -> Iterable[Submission]` where `listing_spec` is one of `"new"`, `"top:day|week|month|year|all"`, `"hot"`. Yields `praw.models.Submission` objects.
  - `expand_thread(submission, more_expand_limit) -> tuple[Post, list[Comment]]` calls `submission.comments.replace_more(limit=more_expand_limit)` and walks the tree breadth-first, producing a flat list of `Comment` dataclasses with `(id, parent_comment_id, depth)`. Comments are emitted in tree-walk order — parents before children — so FK enforcement at insert time is satisfied row by row. Note: `more_expand_limit` is the maximum number of `MoreComments` stubs to expand, *not* a tree-depth cap — PRAW's argument semantic.
- **`ratelimit.py`** — Single function `observe(client) -> RateLimitState` that reads PRAW's exposed rate-limit headers and returns a small dataclass with `remaining`, `used`, `reset_in_seconds`. The ingest loop checks this between subs and aborts the next sub if `remaining < THRESHOLD` (default 10). PRAW already sleeps proactively before hitting the cap; this is a defensive abort to avoid stuck runs.

`Post` and `Comment` are plain dataclasses defined in `reddit/__init__.py` (or a `reddit/models.py` if it grows). The corpus layer accepts them for writes and *also returns* them for reads (constructed from `sqlite3.Row` at the boundary). One canonical type per concept, used at every layer above `reddit/client.py`. PRAW's types stay confined to `reddit/client.py` and `reddit/ingest.py` — never imported above the `reddit/` boundary, to avoid name shadowing with our `Comment`.

### `reddit_corpus.corpus`

- **`schema.py`** — `SCHEMA_VERSION = 1`, `CREATE_STATEMENTS = [...]`, function `apply_schema(conn)` that runs them in order if `schema_version` table is empty. Also turns on `PRAGMA foreign_keys = ON` per connection (this is a connection-level setting in SQLite, not a database-level one).
- **`posts.py`** — `upsert_post(conn, payload)`, `get_post(conn, post_id)`, `list_posts(conn, sub, since, top_n)`.
- **`comments.py`** — `upsert_comments(conn, post_id, payloads)`, `walk_thread(conn, post_id) -> list[CommentRow]` (returns rows in tree-walk order with depth markers), `search_comments(conn, sub, pattern)`.

All functions take a `sqlite3.Connection` as first argument. The connection's lifecycle is owned by the CLI layer, not the corpus layer.

### `reddit_corpus.cli`

Click subcommand groups (`@click.group()` for the resource layer, `@group.command()` for each leaf). One file per group; `main.py` is the top-level dispatcher.

- **`main.py`** — Top-level click group. Loads config once, opens DB connection, dispatches to the chosen subcommand group, ensures connection is committed/closed at exit.
- **`ingest_cmd.py`** — Holds the two flat top-level commands (`ingest`, `init`). The `ingest` handler iterates over `subreddits × listings`, transactionally upserts each post + its comments together. Logs per-sub summary line (`r/anthropic: 12 new posts, 84 comments, 1.4s, rate budget 87/100`).
- **`posts_cmd.py`** — `posts list`, `posts show`.
- **`thread_cmd.py`** — `thread show`.
- **`comments_cmd.py`** — `comments search`.
- **`subs_cmd.py`** — `subs list`.
- **`auth_cmd.py`** — `auth test`.
- **`render.py`** — Two renderers per row type (post, comment-tree). `--format md` (default) produces compact markdown shaped for LLM consumption; `--format json` produces a stable shape mirroring the schema for pipelines. Shared by all read commands.

### `config.py`

- Resolves the data directory using `platformdirs.user_data_dir("reddit-corpus")`.
  - Windows: `%APPDATA%\reddit-corpus\`
  - Linux: `~/.local/share/reddit-corpus/`
  - macOS: `~/Library/Application Support/reddit-corpus/`
- Reads `config.toml` from that directory (or the path given by `--config` / `REDDIT_CORPUS_CONFIG`).
- Returns a `Config` dataclass with all knobs resolved (env > CLI flag > config file > built-in default).

---

## Data flow — ingest run

```
1. CLI 'ingest' invoked
2. config = load_config(env, flags, file)
3. conn = open_db(config.db_path)   # creates + applies schema if missing
4. client = build_praw_client(config.reddit)
5. for sub in config.subreddits (or --sub override):
     ensure_subreddit_row(conn, sub)
     for listing_spec in config.listings (or --listings override):
       for submission in pull_listing(client, sub, listing_spec):
         post_payload, comment_payloads = expand_thread(submission, config.more_expand_limit)
         with conn:                  # implicit transaction
           upsert_post(conn, post_payload)
           upsert_comments(conn, post_payload.id, comment_payloads)
       observe rate limit; abort sub-loop if < threshold
     update subreddit.last_ingested_at
6. log summary, close connection, exit 0
```

Single transaction per `(post + its comments)` ensures we never commit a half-ingested thread. If PRAW raises mid-ingest, that post's transaction rolls back and we move on.

---

## SQLite schema (v1)

```sql
CREATE TABLE schema_version (version INTEGER NOT NULL);
INSERT INTO schema_version VALUES (1);

CREATE TABLE subreddits (
  name TEXT PRIMARY KEY,                     -- ALWAYS canonical lowercase, no prefix. Identity.
  display_name TEXT NOT NULL,                -- Reddit's preferred casing for rendering ("Anthropic", "AskHistorians", ...)
  first_seen_at INTEGER NOT NULL,
  last_ingested_at INTEGER
);

CREATE TABLE posts (
  id TEXT PRIMARY KEY,                       -- Reddit base36 id, e.g. '1abcdef'
  subreddit TEXT NOT NULL REFERENCES subreddits(name),
  author TEXT,                               -- nullable: '[deleted]' authors stored as NULL
  title TEXT NOT NULL,
  selftext TEXT,                             -- empty string for link posts
  url TEXT,                                  -- external URL or self-link
  score INTEGER NOT NULL,                    -- latest fetched
  num_comments INTEGER NOT NULL,
  flair TEXT,
  created_utc INTEGER NOT NULL,              -- unix seconds
  is_self INTEGER NOT NULL,                  -- 0 / 1
  is_locked INTEGER NOT NULL,                -- 0 / 1
  removal_status TEXT NOT NULL CHECK (removal_status IN ('present','deleted_by_author','removed_by_mod','removed_other')),
  crosspost_parent_id TEXT,                  -- NULL = original post; otherwise Reddit id of the post this was crossposted from (may or may not exist locally; NO FK)
  fetched_at INTEGER NOT NULL                -- unix seconds; updated on every encounter (last successful fetch of this row)
);

CREATE INDEX posts_sub_created ON posts(subreddit, created_utc DESC);
CREATE INDEX posts_sub_score   ON posts(subreddit, score DESC);
CREATE INDEX posts_crosspost_parent ON posts(crosspost_parent_id) WHERE crosspost_parent_id IS NOT NULL;

CREATE TABLE comments (
  id TEXT PRIMARY KEY,
  post_id TEXT NOT NULL REFERENCES posts(id),
  parent_comment_id TEXT REFERENCES comments(id) ON DELETE CASCADE,  -- NULL = top-level (parent is the post itself); non-NULL = parent is another comment in this table
  author TEXT,
  body TEXT NOT NULL,                        -- placeholder text from Reddit when removed/deleted
  score INTEGER NOT NULL,
  created_utc INTEGER NOT NULL,
  depth INTEGER NOT NULL,                    -- 0 for top-level, 1 for first reply, ...
  removal_status TEXT NOT NULL CHECK (removal_status IN ('present','deleted_by_author','removed_by_mod','removed_other')),
  fetched_at INTEGER NOT NULL
);

CREATE INDEX comments_post   ON comments(post_id, created_utc);
CREATE INDEX comments_parent ON comments(parent_comment_id);
```

**Notes**:

- Timestamps are UTC unix seconds (INTEGER). SQLite has no native datetime type; epoch ints are unambiguous and sort correctly across platforms. Renderers convert to local-time strings at display time only.
- Booleans are stored as INTEGER 0/1 (SQLite convention).
- `PRAGMA foreign_keys = ON` is set per connection in `config.py` when opening the database. Without this PRAGMA, FK constraints are declared but not enforced.
- `removal_status` is a 4-valued enum (`present` / `deleted_by_author` / `removed_by_mod` / `removed_other`) populated from PRAW's `removed_by_category` at fetch time. Deliberately NOT collapsed to a boolean — see CONTEXT.md "Removal status" entry. The `body` / `author` columns still capture Reddit's placeholder text for any non-`present` row; we don't try to recover the original content.
- No content-hash column — drift policy is overwrite, edits are silently lost.
- `fetched_at` updates on **every encounter**, not only on change. The ingester is one `INSERT OR REPLACE` per row. The column means "last time the ingester wrote this row" — useful as a freshness oracle for the `subs` admin command and future `prune` commands.
- **Vanished content stays as last seen.** If a post we ingested last week no longer appears in `/new` (it's just old), or a comment has been admin-deleted between fetches, we do nothing. The row keeps its old `fetched_at` and old data. We do not maintain a separate `last_seen_at` column or attempt to track disappearance.
- No snapshot / score-history table — same reason.
- Schema is versioned via `schema_version` for future migrations, but v1 has no migration path and assumes a clean DB. If schema needs to change, the v1 plan is "drop the file and re-ingest" (acceptable at personal-corpus scale).

---

## CLI surface

Single binary `reddit-corpus`, exported as a console script in `pyproject.toml`. Resource-grouped subcommands (the `kubectl` / `gh` pattern) for read operations, plus flat top-level commands for system-level operations.

### Top-level (system)

```
reddit-corpus ingest
    [--sub SUB[,SUB,...]]                  # override config.subreddits
    [--listings new,top:week]              # override config.listings
    [--more-expand-limit 32]               # override config.more_expand_limit; "none" = unbounded
    [--dry-run]                            # fetch but don't write

reddit-corpus init                         # create DB + apply schema; safe to run multiple times
```

### `posts` group

```
reddit-corpus posts list --sub SUB
    [--since 7d | --since 2026-04-01]
    [--top N]                              # default: all
    [--sort score|created]                 # default: score
    [--format md|json]                     # default: md

reddit-corpus posts show POST_ID
    [--with-comments]                      # default: false (just the post)
    [--format md|json]
```

### `thread` group

```
reddit-corpus thread show POST_ID          # post + full comment tree (replaces the old `thread POST_ID` and `show-post --with-comments` alias)
    [--format md|json]
```

### `comments` group

```
reddit-corpus comments search --sub SUB --pattern REGEX
    [--in posts|comments|both]             # default: both
    [--limit N]                            # default: 50
    [--format md|json]
```

### `subs` group

```
reddit-corpus subs list                    # tracked subreddits with row counts and last-ingested timestamps
```

### `auth` group

```
reddit-corpus auth test                    # verify Reddit OAuth credentials work
```

### Output examples

**`thread <id>` markdown:**

```markdown
# r/anthropic — "Title goes here"
**u/author** • ▲142 • 3h ago • [link](https://reddit.com/r/anthropic/comments/abc/...)

Selftext body if any.

## Comments (37)

### u/user1 ▲42 2h
Top-level comment body.

  ### u/user2 ▲17 1h *(reply)*
  Nested reply body.

    ### u/user3 ▲5 30m *(reply)*
    Deep reply.

### u/user4 ▲8 2h
Another top-level comment.
```

**`thread <id>` JSON** mirrors the schema directly with a `comments` array of objects keyed by `id` and ordered by tree-walk traversal (parents before children).

---

## Rate limiting & error handling

- **PRAW does the heavy lifting.** It honors Reddit's `X-Ratelimit-*` response headers and sleeps proactively when approaching the per-account cap (100 QPM authenticated). We do not implement custom backoff on top of PRAW — that is wheel-reinvention.
- **Observation, not retry.** `ratelimit.observe(client)` reads the latest rate-limit state and logs at INFO between subs. If `remaining < 10` (configurable threshold), the loop aborts the next sub and exits cleanly (exit code 0, summary logged) so the next scheduled run can pick up.
- **Transient API errors (`prawcore.ServerError`, 5xx):** retry once with 2-second sleep, then propagate.
- **Auth errors (401 / 403):** no retry. Print a short, user-actionable message ("refresh token rejected — see README §Re-authenticating") and exit 1.
- **Network errors (`requests.ConnectionError`):** 3 retries, exponential backoff (1s, 4s, 16s).
- **Per-post failures** are caught and logged; the loop continues. One bad post does not abort the whole run.
- **Logging:** stdlib `logging` to stderr. Default level INFO. `--log-level DEBUG|INFO|WARNING|ERROR` and `REDDIT_CORPUS_LOG=DEBUG` env override. No file logging in v1 — the user can redirect stderr if they want a logfile.

---

## Testing strategy

`pytest` from Slice 1. Three tiers of test, all hermetic except the live test.

### Unit — `corpus/`

- In-memory SQLite (`sqlite3.connect(":memory:")`).
- Apply schema once per fixture, hand-craft `Post` / `Comment` dataclass instances, assert upserts and queries do the right thing.
- Should run in milliseconds. No I/O, no network.

### Unit — `reddit/`

- Mock PRAW. Two viable approaches:
  - **`betamax`** (or similar VCR library against `prawcore`) — record real responses once, replay on test runs. Best fidelity. Adds a dev-only dependency.
  - **Hand-rolled fakes** — small `FakeReddit` / `FakeSubmission` classes that satisfy the shape PRAW exposes. Zero dependencies. Lower fidelity.
- Pick at scaffold time; both are reasonable.
- Either way: zero live-network calls in CI.

### CLI

- `click.testing.CliRunner` (or `typer.testing.CliRunner`) against a tmpdir DB seeded with fixture rows.
- Verifies argument parsing, output rendering (markdown + JSON), exit codes.
- End-to-end without network.

### Live integration test (one)

- Single test, gated behind `REDDIT_CORPUS_LIVE=1` environment variable. Skipped by default (and in CI).
- Hits `r/anthropic`, pulls 1 post + comments, asserts the plumbing works end-to-end against real Reddit.
- Run manually after dependency upgrades or refactors that touch `reddit/`.

### Single-test runs

The test framework must support `pytest tests/path/to/test_x.py::TestClass::test_method` for fast TDD cycles. `pytest` does this natively; verify in Slice 1.

---

## Config & secrets

### `config.toml` (in platform data dir, gitignored)

```toml
[reddit]
client_id     = "abc123..."
client_secret = "xyz..."
refresh_token = "..."
user_agent    = "reddit-corpus/0.1 by u/yourhandle"

[ingest]
subreddits = ["anthropic"]
listings   = ["new", "top:week"]
more_expand_limit = 32           # max MoreComments stubs to expand per post; "none" for unbounded

[paths]
db_path = "default"              # "default" = platform data dir; otherwise an absolute path
```

### Precedence

For each setting, resolved in order: **env var → CLI flag → config file → built-in default**. Env wins so a user can override without touching files (useful in scheduled runs).

### Env vars

```
REDDIT_CORPUS_CLIENT_ID
REDDIT_CORPUS_CLIENT_SECRET
REDDIT_CORPUS_REFRESH_TOKEN
REDDIT_CORPUS_USER_AGENT
REDDIT_CORPUS_DB                 # absolute path to the .db file
REDDIT_CORPUS_CONFIG             # absolute path to config.toml
REDDIT_CORPUS_LOG                # log level (DEBUG/INFO/WARNING/ERROR)
```

### Auth flow

PRAW's refresh-token flow against a "script" or "installed" app registered at https://www.reddit.com/prefs/apps. README documents:

1. Register app → record `client_id` and `client_secret`.
2. One-time OAuth dance (using PRAW's `Reddit.auth.url` + browser redirect) → record `refresh_token`.
3. Drop credentials into `config.toml` or the env.
4. Run `reddit-corpus auth test` to verify.

After step 3 the tool is fully headless. The README is the support contract for re-authentication.

---

## Cross-platform

- **Paths:** `pathlib.Path` everywhere. `platformdirs` (single small dependency, MIT, mature) for data-dir resolution.
- **No platform-specific glue:** no `.bat`, `.ps1`, `.sh` shipped in the repo. The user wires their own scheduler (Task Scheduler / cron / launchd / systemd) per host. The README has copy-pasteable invocation examples for each, but they are documentation only — not part of the package.
- **CI matrix:** GitHub Actions on `windows-latest`, `ubuntu-latest`, `macos-latest`. The smoke-test slice (Slice 1) verifies the package imports and `pytest` passes on all three.
- **Line endings:** rely on `.gitattributes` with `* text=auto`. No manual normalization.
- **Gitignore:** `.venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `*.cassette`, `corpus.db`, `config.toml` (template lives at `config.example.toml`), `dist/`, `*.egg-info/`.

---

## Out of scope (v1)

Restating the non-goals from `requirements.md` so they don't creep in during slice planning:

- No web UI, no HTTP API, nothing network-facing.
- No redistribution of collected content.
- No fine-tuning loops, no embedding pipelines, no vector DB.
- No real-time streaming or websockets.
- No deployment automation. The user wires their own scheduler.
- No multi-user support.
- No automatic schema migrations — schema v2 (if it happens) ships with explicit migration tooling, not implicit `ALTER TABLE` on startup.
- No drift tracking, no score-history table — drift policy is overwrite.

---

## Glossary

> **The canonical project glossary lives at `CONTEXT.md` at the repo root.**
> Terms previously listed inline in this document — Corpus, Drift policy,
> Listing spec, More-expand limit — have been promoted there alongside the
> 2026 additions (Comment forest, Tree-walk order, Orphan Comment, Data API,
> Devvit, Responsible Builder Policy, Script app, Refresh token, Reddit
> credentials). The single non-promoted entry below is for the third-party
> library, which sits outside the project's own domain language.

- **PRAW** — Python Reddit API Wrapper, the canonical OAuth-aware Reddit client (https://praw.readthedocs.io). Handles auth, pagination, rate-limit headers. Third-party dependency, not project-domain vocabulary; see `CONTEXT.md` for in-project terms.
