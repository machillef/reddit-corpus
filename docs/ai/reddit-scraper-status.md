# reddit-scraper — Status

> **Canonical terms live in `CONTEXT.md` at the repo root. Foundational decisions live in `docs/adr/`.** Read `CONTEXT.md` before reasoning about the data model, naming, or domain language; if a word here conflicts with `CONTEXT.md`, `CONTEXT.md` wins. The schema in `reddit-scraper-design.md` already reflects the resolved glossary as of 2026-04-26 — see "Domain-model grilling session" entry below for the change log.

## Initiative
- **Name:** reddit-scraper
- **Type:** Greenfield project
- **Stack:** Python 3.13+/uv/click/praw/sqlite3/platformdirs/pytest/ruff/ty
- **Created:** 2026-04-26
- **Phase:** Bootstrap complete — ready for first slice

## Requirements summary
A personal, cross-platform Reddit corpus tool with two cooperating parts: a `praw`-based ingester that pulls posts and full comment trees from configurable subreddits on a user-chosen schedule and writes them to a local SQLite store, and a thin CLI designed for LLM invocation that exposes ergonomic structured queries over that corpus. Source of truth is a private GitHub repo cloned to Windows / Linux / macOS hosts; runtime artifacts (the SQLite file, OAuth secrets) stay out of git. Non-goals: any network-facing surface, content redistribution, real-time streaming, or deployment automation.

## Bootstrap progress
- [x] Step 1 — Requirements capture → `reddit-scraper-requirements.md`
- [x] Step 2 — Design exploration → `reddit-scraper-design.md`
- [x] Step 3 — Stack decision → `reddit-scraper-decisions.md`
- [x] Step 4 — Scaffold + CLAUDE.md
- [x] Step 5 — Initiative docs (plan, slices)
- [x] Step 6 — Agent wiring
- [x] Step 6b — User-story traceability
- [x] Step 7 — Controlled stop

When all checkboxes are ticked and Step 7's structured output has been emitted, flip the Phase line to `Bootstrap complete — ready for first slice`.

## Slice Status

| #  | Slice                                                      | Status      |
|----|------------------------------------------------------------|-------------|
| 0  | Bootstrap (requirements / design / decisions / scaffold)   | Complete    |
| 1  | Push to GitHub + cross-platform CI matrix                  | Complete    |
| 2  | Pre-flight check script                                    | Complete    |
| 3  | SQLite schema and DAOs                                     | Complete    |
| 4  | Config layer                                               | Complete    |
| 5  | Reddit auth + listing pull (no comments yet)               | Complete    |
| 6  | Comment-tree expansion (`expand_thread`)                   | Complete    |
| 7  | Full ingest pipeline (`cli/ingest_cmd.py` + `init`)        | Complete    |
| 8  | Read-side query commands (posts, thread, comments, subs)   | Complete (JSON only; markdown lands in Slice 9) |
| 9+ | (sketched in `plan.md`; detailed JIT by `arc:continue`)    | —           |

## Constraints
- Cross-platform: runs unchanged on Windows / Linux / macOS from a single codebase.
- Source of truth is a private GitHub repo; runtime artifacts (SQLite DB, secrets, logs) stay gitignored.
- Reddit official API only via `praw`; no HTML scraping fallback.
- Rate limits (100 QPM authenticated) are non-negotiable; back off on 429 / X-Ratelimit-Remaining: 0.
- Secrets (`client_id`, `client_secret`, OAuth tokens) live outside the repo.
- Subreddit selection must be configurable (file/constant) and overridable via CLI args. Initial test target: `r/anthropic`.
- **Reddit credentials require pre-approval (Responsible Builder Policy, late 2025).** Self-service `reddit.com/prefs/apps` is gated; submissions silently fail until the account is approved through Reddit's Developer Support form (~7-day target). See `docs/adr/0002-reddit-api-pre-approval.md`.

## Active blockers
- **Reddit API credentials pending approval.** As of 2026-04-26 the user has filed (or is in the process of filing) an application via Reddit's Developer Support form per ADR 0002. No code changes required while we wait — Slices 1–5 are runtime-complete and the credentials drop-in is unchanged. **Slices 6+ (live ingest) cannot be acceptance-tested against real Reddit until credentials arrive.** Pure-unit tests against PRAW fakes continue to pass and CI matrix is unaffected.

---

<!--
Per-slice entries follow this header, one per slice, appended during execution.
Format: see skills/execution-loop/assets/status-entry.md
-->

## Slice 0: Bootstrap
Status: Complete
Last updated: 2026-04-26

### What was implemented
- `docs/ai/reddit-scraper-requirements.md` — what we're building, scale, constraints, ecosystem, non-goals.
- `docs/ai/reddit-scraper-design.md` — approved architecture (3-layer package, data flow, SQLite v1 schema, CLI surface, rate-limit & error policy, testing strategy, config & secrets, cross-platform notes, glossary).
- `docs/ai/reddit-scraper-decisions.md` — stack decision (Python 3.13+, uv, click, praw, sqlite3, platformdirs, pytest, ruff, ty); prereq-check decision; scaffold decision with installed versions.
- `docs/ai/reddit-scraper-plan.md` — phases (Foundation / Ingest / Query / Polish), assumptions, validation strategy, rollback posture.
- `docs/ai/reddit-scraper-slices.md` — detailed plans for Slices 1-5.
- `pyproject.toml` (PEP 621, `requires-python = ">=3.13"`, build backend `uv_build`, `[project.scripts] reddit-corpus = "reddit_corpus:main"`).
- `src/reddit_corpus/__init__.py` (stub `main()` until Slice 5 replaces it with a click app).
- `tests/__init__.py`, `tests/test_smoke.py` (2 placeholder tests, both passing).
- `.gitignore` (extended for `corpus.db`, `config.toml`, tool caches), `.gitattributes` (line-ending normalization), `.python-version` (3.13).
- `CLAUDE.md` (project facts), `README.md` (install + planned usage + docs index).

### What was validated
- `uv run pytest -v` → 2 passed in 0.03s.
- `uv run pytest tests/test_smoke.py::test_main_callable_exists` → 1 passed (single-test isolation works).
- `uv run ruff check .` → All checks passed.
- `uv run ruff format --check .` → 3 files already formatted.
- `uv run ty check` → All checks passed.
- `uv run reddit-corpus` → "Hello from reddit-corpus!" (entry point fires).

### What remains unverified
- CI matrix on Windows / Linux / macOS — not stood up yet (Slice 1).
- Cross-platform path resolution via `platformdirs` — not exercised yet (Slice 4).
- Live Reddit OAuth — not exercised yet (Slice 5).
- The repo is local-only; no GitHub remote — added as Slice 1 prerequisite.

### Domain-model grilling session (2026-04-26)
Eight design questions were grilled and their resolutions are captured in `CONTEXT.md` and `docs/adr/0001-corpus-as-notebook.md`. Net schema/CLI changes vs the originally-approved design (all reflected in `design.md`):
1. **Corpus stance: notebook, not mirror.** ADR-0001 captures the rationale.
2. **`is_removed` boolean → `removal_status` 4-valued enum** (`present`, `deleted_by_author`, `removed_by_mod`, `removed_other`).
3. **`comments.parent_id` → `parent_comment_id`** with FK to `comments(id) ON DELETE CASCADE`. Comments inserted in tree-walk order so FK is satisfied row-by-row.
4. **Subreddit identity:** lowercase canonical primary key + permissive input parsing + `display_name` column for rendering.
5. **`fetched_at`:** updates on every encounter (last successful row write); vanished content stays as last seen; no `last_seen_at` column.
6. **Crossposts:** added nullable `crosspost_parent_id` column on `posts` (no FK; soft pointer to a Reddit id that may not be local). Partial index where not NULL.
7. **CLI shape:** subcommand groups (`posts list`, `thread show`, `comments search`, `subs list`, `auth test`) for read commands; flat top-level for `ingest` / `init`. Removed the `show-post --with-comments` ↔ `thread` alias.
8. **Type naming:** dropped `PostPayload` / `CommentPayload`. Canonical types are `Post` and `Comment`, used at every layer above `reddit/client.py`.

The schema in `design.md` is now v1-frozen (no further changes expected before Slice 3 implements it). `CONTEXT.md` and `docs/adr/0001-corpus-as-notebook.md` exist and are referenced from `CLAUDE.md` so future sessions pick them up.

### Blockers
None.

### Next recommended step
Run `/arc:continue reddit-scraper` to start Slice 1 (push to private GitHub repo + CI matrix). The first action of Slice 1 will be to confirm the GitHub username/org and target repo name with the user before creating the remote.

---

## Slice 1: Push to GitHub + cross-platform CI matrix
Status: Partial — CI YAML committed locally; GitHub push deferred (needs user confirmation of owner/name)
Last updated: 2026-04-26

### What was implemented
- `.github/workflows/ci.yml` — matrix on `windows-latest` / `ubuntu-latest` / `macos-latest`, Python 3.13, uses `astral-sh/setup-uv@v3`, runs `uv sync` → `ruff check` → `ruff format --check` → `ty check` → `pytest -v`. Triggers on push and PR for `main` and `master`.

### What was validated
- Local quality gates clean: `uv run ruff check .` ✓, `uv run ruff format --check .` ✓, `uv run ty check` ✓, `uv run pytest` ✓ (2 passed).

### What remains unverified
- GitHub repo does not exist yet — needs user to confirm owner/name and run `gh repo create`. This is the only blocker for "Done when" criterion.
- CI matrix has not been exercised on a real push.

### Blockers
None. Repo created at <https://github.com/machillef/reddit-corpus> on 2026-04-26 and CI matrix triggered on first push.

---

## Slice 2: Pre-flight check script
Status: Complete
Last updated: 2026-04-26

### What was implemented
- `scripts/check_prereqs.py` — stdlib-only Python pre-flight (3.13+ check, `uv` PATH check, OS-specific install hints).
- `scripts/check-prereqs.sh` — POSIX shim. Resolves `python3` or `python`, prints clear failure when neither is found, otherwise exec's the `.py`.
- `scripts/check-prereqs.ps1` — PowerShell shim. Same pattern via `Get-Command`, errors out when no python is present.
- `tests/unit/__init__.py` (new package marker), `tests/unit/test_check_prereqs.py` — 11 hermetic tests covering version helpers, install hints, run() exit codes for happy/sad paths on each OS, `shutil.which` boundary.
- `README.md` — added shim invocation snippets for each OS.

### What was validated
- `uv run pytest -q` → 13 passed (2 smoke + 11 new).
- `uv run ruff check .` ✓, `uv run ruff format --check .` ✓, `uv run ty check` ✓.
- `uv run python scripts/check_prereqs.py` on this Windows host → `[ok] Python 3.13.13`, `[ok] uv is on PATH`, exit 0.

### What remains unverified
- Manual run of the `.sh` shim on a real Linux/macOS host.
- Manual run of the `.ps1` shim on a fresh Windows shell.
- The "no python on PATH" failure path of either shim — only verifiable by altering PATH manually.

---

## Slice 3: SQLite schema and DAOs
Status: Complete
Last updated: 2026-04-26

### What was implemented
- `src/reddit_corpus/reddit/__init__.py` — canonical `Post` and `Comment` frozen dataclasses (slots), `RemovalStatus` Literal alias.
- `src/reddit_corpus/corpus/__init__.py` — re-exports the three submodules.
- `src/reddit_corpus/corpus/schema.py` — `SCHEMA_VERSION = 1`, `CREATE_STATEMENTS`, `apply_schema(conn)` that:
  - Sets `PRAGMA foreign_keys = ON` per connection.
  - Registers a Python REGEXP function for SQLite (used by `comments search`).
  - Creates all tables/indexes idempotently and inserts the version row only if missing.
- `src/reddit_corpus/corpus/posts.py` — `upsert_post`, `get_post`, `list_posts(sub, since=, top_n=, sort=)` with `score` / `created` sort and a `ValueError` on invalid sort.
- `src/reddit_corpus/corpus/comments.py` — `upsert_comments` (caller-ordered), `walk_thread` (Python tree-walk for portability over CTEs at v1 scale), `search_comments` joining on `posts` and using REGEXP.
- `tests/unit/test_schema.py` (7 tests), `tests/unit/test_posts.py` (12 tests), `tests/unit/test_comments.py` (8 tests).

### What was validated
- `uv run pytest -q` → 40 passed.
- `uv run ruff check .` ✓, `uv run ruff format --check .` ✓, `uv run ty check` → All checks passed (after annotating fixtures with `Iterator[sqlite3.Connection]` and tightening `_post`/`_comment` factory typing).
- FK rejection paths exercised (orphan comment, unknown subreddit on post insert).
- REGEXP wired correctly: `'claude code' REGEXP 'claude'` → 1.

### What remains unverified
- Real-thread tree-walk fidelity at depth > 5 (deferred until Slice 6 produces live data).
- REGEXP flag semantics (case sensitivity behavior) — to be decided when CLI search command lands in Slice 8.
- See `.claude/loop-qa.local.md` for the QA list.

---

## Slice 4: Config layer
Status: Complete
Last updated: 2026-04-26

### What was implemented
- `src/reddit_corpus/config.py` — `Config`, `RedditAuth`, `IngestSettings`, `Paths` frozen dataclasses; `ConfigError`; `default_data_dir()` / `default_db_path()` via `platformdirs`; `load_config(env, cli_overrides, file_path)` resolving env > CLI > file > default; `to_dict()` redacting secrets to `"***"`; `redact(config)` helper.
- `tests/unit/test_config.py` — 11 tests across precedence layers, missing-secret error path, default vs absolute db_path, redaction.
- `config.example.toml` — checked-in template referenced by README; secrets gitignored, this template is the documented setup file.

### What was validated
- `uv run pytest -q` → 51 passed.
- `uv run ruff check .` ✓, `uv run ruff format --check .` ✓, `uv run ty check` ✓.
- Precedence verified for both `client_id` (env beats CLI beats file) and `db_path` (env override beats file).
- Secret redaction verified at value level: secret values absent from JSON dump, keys still present for shape legibility.

### What remains unverified
- Cross-platform path resolution beyond this Windows host. CI matrix in Slice 1 will exercise it on Linux/macOS once that slice's GitHub push completes.
- See `.claude/loop-qa.local.md`.

---

## Slice 5: Reddit auth + listing pull (no comments yet)
Status: Complete
Last updated: 2026-04-26

### What was implemented
- `src/reddit_corpus/reddit/client.py` — `build_client(config) -> praw.Reddit` (refresh-token auth) + `canonicalize_subreddit(name)` (strips URL/prefix forms, lowercases, validates non-empty).
- `src/reddit_corpus/reddit/ingest.py` — `parse_listing_spec("new"|"hot"|"top[:WINDOW]")` and `pull_listing(client, sub, listing_spec, *, fetched_at, limit=None)` that emits canonical `Post` dataclasses. Removal-status mapping for PRAW's `removed_by_category`. Crosspost-parent fullname stripping (`t3_xxx` → `xxx`).
- `src/reddit_corpus/reddit/ratelimit.py` — `RateLimitState(remaining, used, reset_timestamp)` and `observe(client)` (defensive against missing fields), plus `should_pause(state, threshold=10)`.
- `src/reddit_corpus/cli/__init__.py`, `cli/main.py`, `cli/auth_cmd.py` — top-level click app with `auth test`. The CLI accepts a `client_builder` from `ctx.obj` for hermetic testing; defaults to `build_client`.
- `src/reddit_corpus/__init__.py` — `main = cli` re-export so the `reddit-corpus` console script dispatches into click.
- `tests/fakes/__init__.py`, `tests/fakes/praw_fakes.py` — `FakeReddit`, `FakeSubreddit`, `FakeSubmission`, `FakeAuth`, `FakeListings`, `make_fake_reddit_with`.
- `tests/unit/test_reddit_client.py`, `test_reddit_ingest.py`, `test_ratelimit.py`, `test_cli_auth.py` — 29 new tests covering client construction, sub canonicalization, listing-spec parsing, post mapping, removal-status mapping, crosspost stripping, ratelimit observation/threshold, and the auth CLI happy/sad paths.

### What was validated
- `uv run pytest -q` → 80 passed.
- `uv run ruff check .` ✓, `uv run ruff format --check .` ✓, `uv run ty check` ✓.
- `uv run reddit-corpus --help` and `uv run reddit-corpus auth --help` both render the expected click trees.

### What remains unverified
- Live network call against real Reddit OAuth — manual, gated outside CI. Listed in `.claude/loop-qa.local.md`.
- PRAW `auth.limits` shape stability across PRAW versions — `observe()` is the only place we read it, so future churn is contained.
- Comment-tree expansion (`replace_more`) — explicitly deferred to Slice 6 per `slices.md`.

### Blockers
None — Slices 6+ are sketched in `plan.md` but not detailed; they are out of scope for this loop run.

---

## Review pass (Phase 3)
Status: Complete (2 passes — code review + silent-failure hunter)
Last updated: 2026-04-26

### Reviewer-driven fixes applied this pass
- **MUST-FIX 1 (recursion):** `corpus/comments.py:walk_thread` rewritten as an iterative depth-first traversal so threads deeper than Python's default recursion limit (1000) no longer raise `RecursionError`. Added `test_walk_thread_handles_deeply_nested_threads` (1500-deep chain) as a regression guard.
- **MUST-FIX 2 (FK cascade):** `posts.upsert_post` and `comments.upsert_comments` switched from `INSERT OR REPLACE` to `INSERT … ON CONFLICT(id) DO UPDATE`. Re-ingesting a post that already has comments no longer attempts a DELETE+INSERT and no longer trips the FK on `comments.post_id`. Added `test_re_upsert_post_with_existing_comments_does_not_cascade_delete`.
- **SHOULD-FIX 1 (regex):** `canonicalize_subreddit` regex split into two narrow patterns (`https://reddit.com/...` then `r/`) so a bare name like `rpg` is preserved instead of having its leading `r` stripped. Added `test_canonicalize_subreddit_preserves_bare_name_starting_with_r`.
- **SHOULD-FIX 2 (TOCTOU):** `schema_version.version` gained a `UNIQUE` constraint and `apply_schema` now uses `INSERT OR IGNORE`, removing the check-then-insert race between concurrent opens.
- **SHOULD-FIX 4 (regex error swallowing):** `_regexp` no longer catches `re.error` — malformed patterns surface as `sqlite3.OperationalError` instead of returning empty result sets. Added `test_regexp_propagates_re_error_for_malformed_pattern`.
- **Silent-failure #2 (TOML):** `config._load_file` catches `TOMLDecodeError` and re-raises as `ConfigError(f"Could not parse {path}: …")` so the CLI's friendly handler renders a clear message instead of a raw traceback. Added `test_malformed_toml_raises_config_error`.
- **NICE-TO-HAVE 2 (orphan walk):** added `test_walk_thread_appends_orphans_at_tail` — verifies orphans whose parent comment was admin-deleted between fetches are appended at the tail rather than dropped.
- **NICE-TO-HAVE 3 (fake/real divergence):** `FakeReddit.subreddit` and `make_fake_reddit_with` now delegate to the real `canonicalize_subreddit`, so URL-form inputs in fake-backed tests exercise the same path as production.

### Reviewer findings deferred (not load-bearing for this slice)
- NIT 1 (`list_posts` inline SQL ternary), NIT 2 (`Protocol` for the CLI client builder), NIT 3 (factor `_coerce` out of `observe`), NICE-TO-HAVE 1 (`executemany` batching) — readability tweaks; revisit during a refactor pass when the affected files change for other reasons.
- Silent-failure #3 (`should_pause` returns False on unknown rate-limit state) — flagged for revisit when Slice 6/7 wires the ingest loop and we know what behavior is right at first contact.
- Silent-failure #5 (unknown `removed_by_category` collapses to `removed_other` silently) — revisit when telemetry/logging lands in Slice 12.
- Silent-failure #6 (`auth test`'s broad except gives the same hint for refresh-token vs network failures) — revisit when the CLI gets richer error rendering.

### Final test/quality gate state
- `uv run pytest -q` → 86 passed.
- `uv run ruff check .` ✓, `uv run ruff format --check .` ✓, `uv run ty check` ✓.
