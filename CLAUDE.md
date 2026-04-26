# reddit-corpus

## Stack
Python 3.13+ • uv • click • praw • stdlib sqlite3 • platformdirs • pytest • ruff • ty (beta) • src/ layout

## Build & test
`uv sync` | `uv run pytest`

Quality gates (CI matrix Win/Linux/macOS): `uv run ruff check .` • `uv run ruff format --check .` • `uv run ty check` • `uv run pytest`

## Structure
- `src/reddit_corpus/` — package: `reddit/` (network), `corpus/` (storage), `cli/` (presentation)
- `tests/` — pytest tests; `tests/fixtures/` for shared data
- `scripts/` — pre-flight `check_prereqs.py` + `.sh` / `.ps1` shims
- `docs/ai/` — initiative planning, status, decisions
- Entry point: `reddit-corpus` (declared in `pyproject.toml [project.scripts]`)

## Key patterns
- **Layer direction:** `cli → corpus → reddit`. `corpus` never imports `reddit` (testability).
- **Errors:** stdlib exceptions; PRAW errors caught at `reddit/` boundary, surfaced from CLI with actionable messages.
- **Config:** `platformdirs.user_data_dir("reddit-corpus")` + `config.toml`; precedence env > CLI > file.
- **Secrets:** Reddit OAuth credentials in `config.toml` or env (`REDDIT_CORPUS_*`); both gitignored.
- **DB:** local SQLite, gitignored. Drift policy: overwrite (no score/edit history).

## Source of truth
- `CONTEXT.md` — **canonical domain language and term resolutions** (DDD-style glossary). Read FIRST when reasoning about the data model or naming. If a word in the codebase or design doc conflicts with `CONTEXT.md`, `CONTEXT.md` wins.
- `docs/adr/` — architecture decision records. Read before challenging a foundational design choice; the rationale is captured there.
- `docs/ai/` — initiative planning, status, and decisions for this project
- `~/.claude/CLAUDE.md` — global Python toolchain rules and workflow

Do not store session state or evolving task notes here.

## Start here
1. Read `CONTEXT.md` for canonical domain terms (Notebook, Corpus, Removal status, Subreddit name canonical, Subreddit display name, Fetched-at, Crosspost parent id, Subcommand group, Post / Comment, Parent-comment-id).
2. Read `docs/ai/reddit-scraper-status.md` for current slice.
3. Read `docs/ai/reddit-scraper-slices.md` for scope.
4. Read `docs/ai/reddit-scraper-design.md` for architecture.
5. Skim `docs/adr/` if the slice touches a foundational area.
