# Plan: reddit-scraper

> **Status as of 2026-04-26.** Phases 1, 2, and 3 are complete (Slices 1–10).
> The remaining work is Phase 4: Slice 11 (live integration test, blocked on
> Reddit credentials per ADR 0002) and Slice 12 (logging polish, scheduler
> example docs). See `docs/ai/reddit-scraper-status.md` for live per-slice
> state.

## Phases

### Phase 1 — Foundation (Slices 1-4) — Complete
Stand up the cross-platform infrastructure and the storage layer that the rest of the system writes against.
- **Slice 1** — Push to a private GitHub repo and stand up the CI matrix (Win / Linux / macOS) running quality gates against the existing scaffold. Proves cross-platform from day one.
- **Slice 2** — Pre-flight check script (`scripts/check_prereqs.py` + `.sh` / `.ps1` shims). User-requested.
- **Slice 3** — SQLite schema layer (`corpus/schema.py` + `corpus/posts.py` + `corpus/comments.py`). Pure-DB unit tests with `:memory:`. No network anywhere.
- **Slice 4** — Config layer (`config.py`) with `platformdirs`, env/CLI/file precedence, `config.toml` shape. Gitignored `config.toml`; checked-in `config.example.toml`.

### Phase 2 — Ingest path (Slices 5-7) — Complete
Get data from Reddit into SQLite end-to-end.
- **Slice 5** — Reddit auth and listing pull (`reddit/client.py` + `reddit/ingest.py` for `/new` only, no comments). Hand-rolled PRAW fakes for tests. `auth test` CLI subcommand.
- **Slice 6** — Comment-tree expansion (`reddit/ingest.py` calls `replace_more` and walks the tree). `more_expand_limit` config knob. Tests with deeper fakes.
- **Slice 7** — Full ingest end-to-end — `cli/ingest_cmd.py` wires `reddit → corpus → DB`. Per-post transactions, per-sub summary logging, rate-limit observation. CLI integration tests against fakes.

### Phase 3 — Query path (Slices 8-10) — Complete
LLM-facing query surface over the corpus.
- **Slice 8** — Read-side query commands (`posts list`, `posts show`, `thread show`, `comments search`, `subs list`) as click subcommand groups. JSON renderer first (deterministic, easy to assert on).
- **Slice 9** — Markdown renderer (`cli/render.py`). Both formats wired to all query commands.
- **Slice 10** — Admin commands (`init`, `subs`). README setup guide for OAuth flow.

### Phase 4 — Production-readiness (Slice 11+) — In progress
- **Slice 11** — Live integration test (gated behind `REDDIT_CORPUS_LIVE=1`), one-shot ingest of `r/anthropic` end-to-end. Skipped in CI; runnable by hand after dependency upgrades. **Blocked on Reddit Data API approval (ADR 0002).**
- **Slice 12** — Polish: `--log-level`, error-message ergonomics, README troubleshooting section, scheduler examples (Task Scheduler / cron / launchd) as documentation only.

---

## Assumptions

These are the load-bearing assumptions; if any turns out wrong, the plan needs revision.

1. **Reddit API access remains available to authenticated personal-use accounts at the current free tier (≤ 100 QPM), *contingent on Reddit-approved credentials*.** As of late 2025 (Responsible Builder Policy rollout), self-service app creation at `reddit.com/prefs/apps` is gated — new apps require manual approval via Reddit's Developer Support form (~7-day target SLA, no guarantees). The non-commercial free tier still exists once approved; we proceed assuming personal-use applications describing this project ("personal LLM-assisted research, no redistribution, no ML training") are routinely granted. **If the application is denied or stalls indefinitely, see `docs/adr/0002-reddit-api-pre-approval.md` for fallback paths (Arctic Shift, RSS, etc.) — none preserve the full PRAW-shaped surface, all require rewriting `reddit/client.py` and `reddit/ingest.py`.**
2. **PRAW continues to be maintained.** The repo was last updated 2026-04-20 (active). If PRAW were abandoned, we'd need to either fork or reimplement the OAuth + rate-limiting layer.
3. **`ty` 0.0.x doesn't introduce breakage that we can't work around in a slice or two.** Beta tooling. Mitigation: documented fallback to mypy in `decisions.md`.
4. **The user accepts manual scheduler wiring on each host.** No automation for Task Scheduler / cron / launchd ships in v1; we provide README examples only.
5. **A single-user, single-corpus, append-only-by-post-id model is enough.** No multi-user, no replication, no encryption-at-rest. If the user shares the SQLite file between machines, it's their responsibility (sync via Syncthing / Dropbox / git LFS — out of scope for the project).

---

## Validation strategy

Each slice has its own done-criterion (in `slices.md`), but the project-level validation is layered:

- **Per-slice gates** (run by `arc:continue` for each slice):
  - `uv run ruff check .`
  - `uv run ruff format --check .`
  - `uv run ty check`
  - `uv run pytest`
- **Cross-platform gate** (run in CI on every push, starting Slice 1): the same four commands on `windows-latest` / `ubuntu-latest` / `macos-latest`.
- **End-to-end smoke** (Slice 11): live test against `r/anthropic`, gated on `REDDIT_CORPUS_LIVE=1`. Run by hand; not in CI.

A slice is "done" only when all four per-slice gates pass on the developer's machine *and* the CI matrix is green.

---

## Rollback posture

- **Per-slice rollback:** revert the slice's commit. The scaffold and `docs/ai/` are sturdy enough that a partial revert is uncommon — slices are sized to be reverted as a unit.
- **Schema rollback (Slice 3+):** drop `corpus.db` and re-ingest. v1 has no migration tooling. The corpus is local and replaceable; this is acceptable at personal-corpus scale.
- **Auth rollback:** if a refresh token is leaked, revoke at https://www.reddit.com/prefs/apps and regenerate. The `auth test` subcommand surfaces 401/403 immediately so revocation is detectable.
- **Catastrophic rollback:** the user keeps a clone on multiple machines (per requirements). Worst-case is "delete this clone, re-clone, re-`uv sync`, re-`auth test`."

---

## Out-of-band tracking

These do not have slice numbers because they're cross-cutting or one-time:

- **GitHub repo creation** — bundled into Slice 1 prerequisite. One-time, human-confirmed action.
- **Reddit OAuth credentials setup** — documented in README, performed by the user on each host. Not code.
- **Scheduler registration** — documented in README, performed by the user. Not code.
- **`.knowledge/` wiki page** — if/when the project produces durable insights worth filing, end-of-session nudge will offer.
