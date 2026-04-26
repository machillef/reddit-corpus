# Slices: reddit-scraper

> **Status as of 2026-04-26: Slices 1–10 are complete.** This file retains the
> *original detailed plans* for Slices 1–5 as a historical record, plus a
> retrospective summary of Slices 6–10 below. The live per-slice "what was
> implemented" / "what was validated" entries are in
> `docs/ai/reddit-scraper-status.md`. Slices 11 and 12 remain sketched in
> `plan.md` and will be detailed by `arc:continue` just-in-time.

---

## Slice 1: Push to GitHub + cross-platform CI matrix
Goal: Prove the scaffold builds and tests pass on Windows, Linux, and macOS via GitHub Actions, and establish the repo as the source of truth across machines.
User stories: 12 (cross-platform), 13 (rate-limit honoring — verified passively by tests not exceeding the budget)
Touched area:
- `.github/workflows/ci.yml` (new)
- A private GitHub repo (created out-of-band; see "Pre-slice action" below)

Tests:
- The CI workflow runs on every push and PR.
- Matrix job: Python 3.13 on `windows-latest`, `ubuntu-latest`, `macos-latest`.
- Each job: `uv sync` → `uv run ruff check .` → `uv run ruff format --check .` → `uv run ty check` → `uv run pytest`.
- The smoke tests in `tests/test_smoke.py` are sufficient for the first green run.

Risk:
- `uv` action may not yet support all three OSes equally. Mitigation: use `astral-sh/setup-uv@v3` (or current latest) which is officially supported.
- Windows path handling could surface in `ty` or `pytest`. Mitigation: the smoke test uses no paths; the scaffold is path-clean.
- Private repo visibility — the user will confirm the GitHub account and repo name before creation.

Pre-slice action (one-time, human-confirmed):
- Confirm GitHub username/org and target repo name with the user.
- `gh repo create <owner>/<name> --private --source=. --push --description "..."`.

Rollback:
- Revert the workflow YAML; delete the GitHub repo if the experiment doesn't work. Local code is unaffected.

Done when:
- A push to `main` (or whatever default branch) triggers the workflow and all three matrix jobs report green in the GitHub Actions tab.

---

## Slice 2: Pre-flight check script
Goal: Provide a standalone check users can run before `uv sync` to verify Python and uv are installed, with OS-specific install instructions on failure.
User stories: 10 (pre-flight check), 12 (cross-platform)
Touched area:
- `scripts/check_prereqs.py` (new) — Python stdlib only
- `scripts/check-prereqs.sh` (new) — POSIX shell wrapper, dispatches to `.py`
- `scripts/check-prereqs.ps1` (new) — PowerShell wrapper, dispatches to `.py`
- `README.md` — first install step references the script
- `tests/test_check_prereqs.py` (new) — unit tests for the script's logic

Tests:
- Mock `sys.version_info` to simulate Python < 3.13 → script exits non-zero with a Python-install hint.
- Mock `shutil.which("uv")` returning None → script exits non-zero with the correct OS-specific install command (Linux/macOS curl line vs Windows PowerShell line).
- Happy path: real Python + uv present → script exits 0.

Risk:
- The shell shims need to handle the case where Python itself is missing. Mitigation: the shims check for `python` / `python3` in PATH first and print a clear "install Python from python.org" message if neither is found, before attempting to dispatch.

Rollback:
- Delete `scripts/`. Revert README.

Done when:
- `python3 scripts/check_prereqs.py` exits 0 with a green summary on this machine.
- The same script exits non-zero with a clear actionable message when run with a missing-uv scenario (test simulates this).
- Unit tests pass: `uv run pytest tests/test_check_prereqs.py`.

---

## Slice 3: SQLite schema and DAOs
Goal: Land the storage layer (`corpus/`) — schema creation, post upserts, comment upserts, basic reads — fully unit-tested with `:memory:` SQLite. No network code anywhere in this slice.
User stories: 1, 4, 5, 6, 9, 11 (everything that depends on storage; the DAOs serve as the contract).
Touched area:
- `src/reddit_corpus/corpus/__init__.py` (new — re-exports)
- `src/reddit_corpus/corpus/schema.py` (new) — `SCHEMA_VERSION`, `CREATE_STATEMENTS`, `apply_schema(conn)`, `PRAGMA foreign_keys = ON`.
- `src/reddit_corpus/corpus/posts.py` (new) — `upsert_post`, `get_post`, `list_posts(sub, since, top_n, sort)`.
- `src/reddit_corpus/corpus/comments.py` (new) — `upsert_comments`, `walk_thread(post_id)`, `search_comments(sub, pattern, in_, limit)`.
- `tests/unit/test_schema.py`, `tests/unit/test_posts.py`, `tests/unit/test_comments.py` (new).

Tests (TDD — write first):
- `apply_schema` on a fresh `:memory:` connection creates all expected tables and indexes; running it twice is idempotent.
- `upsert_post` inserts a new row, then a second call with same id updates the row's score / fetched_at.
- `list_posts` respects `since`, `top_n`, `sort=score|created`.
- `upsert_comments` correctly nests: parent_id NULL for top-level, populated for replies.
- `walk_thread` returns rows in tree-walk order with correct depth values.
- `search_comments` matches a regex across `body`.
- Foreign-key constraints reject orphan comments when `PRAGMA foreign_keys = ON`.

Risk:
- SQLite's `REGEXP` operator is not built-in; need to register a Python function. Mitigation: tests verify this is wired up correctly in `apply_schema` or via a per-connection setup helper.
- Datetime handling: `created_utc` is INTEGER unix seconds. Tests must construct epoch ints directly, not `datetime` objects.

Rollback:
- Revert the slice. The package still imports cleanly (corpus is opt-in via the layer above).

Done when:
- All unit tests in `tests/unit/test_*.py` pass.
- `uv run ty check` is clean on the new modules.
- `uv run ruff check .` and `--format check` are clean.

---

## Slice 4: Config layer
Goal: Centralize config loading — `platformdirs` for paths, env > CLI > file > default precedence, `config.toml` parsing, OAuth credential resolution.
User stories: 3 (TOML config), 11 (init/subs/auth test depend on knowing where the DB is)
Touched area:
- `src/reddit_corpus/config.py` (new) — `Config` dataclass, `load_config(env, cli_overrides, file_path) -> Config`, `default_data_dir()`, `default_db_path()`.
- `config.example.toml` (new, root) — reference shape with placeholder values; checked in.
- `tests/unit/test_config.py` (new).

Tests:
- `default_data_dir()` returns `platformdirs.user_data_dir("reddit-corpus")` — verify it produces the expected path on this OS.
- Loading a config file resolves all expected keys.
- Env vars override file values; CLI overrides override env values.
- Missing required secrets (client_id, etc.) raise a specific actionable exception.
- A `Config` with all defaults filled is JSON-serializable (for debug logging).

Risk:
- `platformdirs` paths differ subtly across OSes; tests must avoid asserting absolute paths and instead assert behavior (file exists, joins are valid, etc.).

Rollback:
- Revert. Storage layer (Slice 3) does not depend on Config — it takes a `Connection` from the caller — so corpus/ remains intact.

Done when:
- All tests pass on this machine, and CI matrix passes on Win/Linux/macOS (since path resolution differs per OS, this is the first slice that meaningfully exercises cross-platform behavior).
- `uv run ty check` clean.
- `config.example.toml` is the documented setup template referenced in README.

---

## Slice 5: Reddit auth + listing pull (no comments yet)
Goal: First slice that touches the network. Build a PRAW client from Config, pull `/new` for one subreddit, return a list of `Post` dataclasses. No comment expansion in this slice.
User stories: 1 (ingest), 2 (subreddit override), 8 (auth test)
Touched area:
- `src/reddit_corpus/reddit/__init__.py` (new — re-exports + dataclass definitions)
- `src/reddit_corpus/reddit/client.py` (new) — `build_client(config) -> praw.Reddit`, sets user_agent, refresh_token auth.
- `src/reddit_corpus/reddit/ingest.py` (new, partial) — `pull_listing(client, sub, listing_spec) -> Iterable[Post]`. Comments deferred to Slice 6.
- `src/reddit_corpus/reddit/ratelimit.py` (new) — `observe(client) -> RateLimitState`.
- `src/reddit_corpus/cli/__init__.py` (new) + `cli/main.py` (new — top-level click group + dispatch) + `cli/auth_cmd.py` (new, holds `auth test`).
- `tests/unit/test_reddit_client.py`, `tests/unit/test_reddit_ingest.py`, `tests/unit/test_ratelimit.py` (new).
- `tests/fakes/praw_fakes.py` (new) — `FakeReddit`, `FakeSubreddit`, `FakeSubmission`.
- The package `__init__.py`'s `main` stub is replaced with a click app dispatcher entry point.

Tests:
- `build_client` constructs a `praw.Reddit` with all expected kwargs given a Config; never hits the network in unit tests (mocked).
- `pull_listing` with a `FakeSubreddit` yields the expected `Post` shape.
- Listing-spec parser: `"new"`, `"top:week"`, `"hot"` parse correctly; invalid specs raise.
- `observe` reads rate-limit state from `client.auth.limits` (or whatever PRAW exposes) and returns the dataclass.
- CLI: `reddit-corpus auth test` against a FakeReddit prints "OK" and exits 0; against a 401 it prints a re-auth hint and exits 1.

Risk:
- PRAW's exposed rate-limit state is not perfectly stable across versions. Mitigation: the `observe` function is the only place we read it, isolating future churn.
- `replace_more` requires a live PRAW Submission; we can't fake it without committing to a fake-shape contract. Mitigation: defer that part to Slice 6 along with the deeper fakes.

Rollback:
- Revert. Storage layer (Slice 3) and config (Slice 4) remain functional.

Done when:
- All unit tests pass without any live network call.
- `reddit-corpus auth test` runs against the user's real refresh token (manual one-shot verification — not in CI).
- CI matrix passes (with the `auth test` integration skipped in CI).
- `uv run ty check` clean across the three new layers.

---

> Slices 6–10 were completed during the same session that delivered Slices 1–5.
> Their detailed "what was implemented" entries live in
> `docs/ai/reddit-scraper-status.md`. A short summary follows for readers who
> want the shape of each slice without leaving this file:
>
> - **Slice 6** — `expand_thread()` in `reddit/ingest.py`. Walks PRAW's comment
>   forest after `replace_more()` and emits `Comment` dataclasses in tree-walk
>   order. Tolerant of orphan parent ids. Deeper PRAW fakes added.
> - **Slice 7** — `cli/ingest_cmd.py`. Wires `reddit → corpus → DB` with
>   per-post transactions, per-post failure isolation, and ratelimit-aware
>   abort between subs. New `corpus/subreddits.py` DAO module. Also ships
>   `init` (idempotent schema apply).
> - **Slice 8** — Read-side query commands: `posts list/show`, `thread show`,
>   `comments search`, `subs list`. JSON renderer. `cli/_common.py` for
>   `parse_since` (relative or ISO date) and shared helpers.
> - **Slice 9** — Markdown renderer in `cli/render.py`. `--format md` becomes
>   the default; `--format json` is opt-in. Removal-status decoration.
> - **Slice 10** — `init` and `subs list` admin commands. Both folded into
>   Slices 7 and 8 rather than getting a dedicated commit, since the surface
>   was small and naturally adjacent to those slices' work.
>
> Slices 11 and 12 remain to do. Slice 11 (live integration test gated on
> `REDDIT_CORPUS_LIVE=1`) is blocked on Reddit credentials per ADR 0002.
> Slice 12 (logging flags, scheduler example docs, README troubleshooting)
> can land any time and does not need credentials.

---

## Agent wiring (per-slice)

Per `skills/execution-loop/references/arc-agents.md`, every slice that touches Python code triggers `arc:python-reviewer`. Specific extras per slice:

| Slice | Agents to invoke after implementation                                                                |
|-------|------------------------------------------------------------------------------------------------------|
| 1     | `arc:python-reviewer` (CI workflow YAML) + `arc:kubernetes-reviewer` if any YAML config is non-trivial; `arc:security-audit` (since the slice creates a remote repo and pushes secrets-relevant code). |
| 2     | `arc:python-reviewer` (Python script) + `arc:powershell-reviewer` (`.ps1` shim).                     |
| 3     | `arc:python-reviewer` + `arc:security-audit` (data persistence layer touches; no secrets here, but DAOs are the layer that *will* hold credentials' downstream effects). |
| 4     | `arc:python-reviewer` + `arc:security-audit` (config + secrets handling).                            |
| 5     | `arc:python-reviewer` + `arc:security-audit` (Reddit OAuth + external API calls).                    |
| 6     | `arc:python-reviewer`.                                                                               |
| 7+    | `arc:python-reviewer` baseline; `arc:security-audit` revisited if/when network or secrets surface.   |

`arc:continue` should consult this table when starting each slice.

---

## Traceability (Step 6b)

Every user story in `design.md` is covered by at least one slice:

| Story | Covered by |
|-------|------------|
| 1 — Ingest configured subreddits | Slices 5, 6, 7 |
| 2 — CLI override of subs/listings | Slices 4, 7 |
| 3 — TOML config | Slice 4 |
| 4 — `posts list` (LLM-facing) | Slice 8 |
| 5 — `posts show` / `thread show` (LLM-facing) | Slice 8 |
| 6 — search (LLM-facing) | Slice 8 |
| 7 — `--format md|json` | Slices 8 (JSON), 9 (Markdown) |
| 8 — `auth test` | Slice 5 |
| 9 — `subs` admin | Slice 10 |
| 10 — Pre-flight check | Slice 2 |
| 11 — `init` admin (schema) | Slices 3, 10 |
| 12 — Cross-platform | Slices 1, 4 |
| 13 — Rate-limit honoring | Slices 5, 7 |
