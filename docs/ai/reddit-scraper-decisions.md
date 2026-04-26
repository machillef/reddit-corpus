# Decisions: reddit-scraper

A running log of architectural and stack decisions made during bootstrap and execution. Each decision has a date, a status (Recommended / Accepted / Superseded), and rationale.

---

## Decision: Stack
Date: 2026-04-26
Status: Accepted (user confirmed YES with prereq-check addendum)

**Language / runtime:** Python 3.13+ (development on 3.14.x; floor is 3.13 to cover both currently-deployed user machines and forward-compatibility through 3.14/3.15)
**Package/dep manager:** uv (≥0.11; verified 0.10.7 present locally — sync target 0.11.x via `pyproject.toml`)
**CLI lib:** click 8.3.x — mature, widely understood, explicit decorators match the design's subcommand structure; avoids the Pydantic transitive dependency that typer brings; the design doc already references `click.testing.CliRunner`.
**Reddit client:** praw 7.7.x
**Storage:** stdlib sqlite3
**Data-dir resolution:** platformdirs 4.9.x
**Test framework:** pytest 9.0.x
**PRAW mocking:** Hand-rolled fakes — lower maintenance than betamax cassettes (no cassette drift when PRAW minor-versions), easier to reason about in CI, and the surface area is small (3-4 PRAW types: `Reddit`, `Submission`, `Comment`, `Subreddit`).
**Lint / format:** ruff (latest)
**Type-check:** ty 0.0.x — beta, breaking changes possible across releases. Accepted risk for a personal project; user's global toolchain preference. Revisit (mypy fallback) if breakage becomes disruptive.
**Project layout:** `src/` layout — isolates package code from project root, prevents accidental local imports in tests, matches the directory tree already drawn in the design doc.
**Scaffold source:** `uv init --package reddit-corpus` then `uv add praw platformdirs click` and `uv add --dev pytest ruff ty` — cross-platform, no cookiecutter dependency, generates PEP 621 `pyproject.toml` with `[project.scripts]` stub.
**CI:** GitHub Actions, matrix on `windows-latest` / `ubuntu-latest` / `macos-latest`.
**Per-job commands:** `uv sync; uv run ruff check .; uv run ruff format --check .; uv run ty check .; uv run pytest`

### Rationale (overall)

Aligns with the user's established Python toolchain (uv / ruff / ty / pytest) and the three-layer architecture from `design.md`. Click is the path of least surprise for a CLI with 8+ subcommands, subcommand groups, and `--format` choices — typer would add Pydantic weight for marginal ergonomic gain on a CLI this size. Hand-rolled PRAW fakes keep tests simple and avoid cassette maintenance overhead; the fake surface is tiny because only `reddit/ingest.py` and `reddit/client.py` ever touch PRAW.

### Alternatives considered & rejected

- **typer** — adds a Pydantic dependency for no clear gain at this CLI's size; the design already references click.
- **betamax cassettes** — higher fidelity than hand-rolled fakes, but require cassette updates on every PRAW release. Overkill given the small mock surface.
- **flat layout (no src/)** — leads to local-import bugs in tests where `import reddit_corpus` resolves against the project root. The src layout sidesteps this.
- **argparse** — stdlib-only and zero deps, but verbose for a CLI with this many subcommands. Click is one small mature dependency with much better ergonomics.

### Revisit if

- CLI grows to 20+ subcommands (consider typer's auto-generated help and type-driven options).
- PRAW mocking becomes brittle across Reddit API changes (revisit betamax for high-fidelity replay).
- We need to publish to PyPI under a different name (revisit project name and `[project.scripts]` entry).
- `ty` 0.0.x breakage becomes disruptive — fall back to `mypy`.

---

## Decision: Prerequisite-check script
Date: 2026-04-26
Status: Accepted (user-requested addition during stack confirmation)

A `scripts/check_prereqs.py` (Python stdlib only — no project deps required to run it) verifies the host has what's needed before `uv sync` is attempted:

1. Python ≥ 3.13 (`sys.version_info`).
2. `uv` on PATH (`shutil.which("uv")`); if missing, prints OS-appropriate install command (curl on Linux/macOS, PowerShell `irm` on Windows, or `pip install uv` fallback).
3. `git` on PATH — informational (the user has already cloned to be running this, but a missing `git` will break dev loop).

Wrapper shims `scripts/check-prereqs.sh` and `scripts/check-prereqs.ps1` give a clearer error than `python: command not found` when Python itself is absent — they detect Python presence, then dispatch to the .py script.

**Why this is a script and not runtime CLI logic:** by the time `reddit-corpus` runs, dependencies are already installed (uv or pip put them there). The realistic failure mode is at *install* time, not run time. A pre-flight script catches it before the user types `uv sync`.

**Slice:** scheduled as Slice 2 (after the smoke-test scaffold slice), since it's small and orthogonal to the ingester / corpus / cli layers. README's first install step will be `python3 scripts/check_prereqs.py` (or the .sh / .ps1 shim).

---

## Decision: Scaffold
Date: 2026-04-26
Status: Accepted

**Source:** `uv init --package --name reddit-corpus --description "..." --python 3.13 .`, followed by `uv add praw platformdirs click` and `uv add --dev pytest ruff ty`.

**Boilerplate removed:** none — applied as-is. The `src/reddit_corpus/__init__.py` `main()` stub remains as the entry-point target until Slice 1 replaces it with a click app.

**Layout produced:**
- `src/reddit_corpus/__init__.py` (package root, holds `main()` for the entry point until Slice 1)
- `pyproject.toml` (PEP 621, `requires-python = ">=3.13"`, `[project.scripts] reddit-corpus = "reddit_corpus:main"`, build backend `uv_build`)
- `.python-version` (`3.13`)
- `tests/test_smoke.py` + `tests/__init__.py` (placeholder so `pytest` collects something; will be replaced by real tests in Slice 1)
- `.gitignore` (extended for `corpus.db`, `config.toml`, tool caches, OS noise)
- `.gitattributes` (`* text=auto eol=lf`, with `*.ps1 eol=crlf` exception for Windows scripts)
- `CLAUDE.md`, `README.md`

**Versions installed (lockfile, 2026-04-26):**
- praw 7.8.1, prawcore 2.4.0
- click 8.3.3
- platformdirs 4.9.6
- pytest 9.0.3, pluggy 1.6.0, iniconfig 2.3.0
- ruff 0.15.12
- ty 0.0.32 (beta — accepted risk per stack decision above)

**Verified:**
- `uv run pytest` — 2 passed
- `uv run pytest tests/test_smoke.py::test_main_callable_exists` — single-test isolation works
- `uv run ruff check .` — clean
- `uv run ruff format --check .` — clean
- `uv run ty check` — clean
- `uv run reddit-corpus` — entry point fires (`Hello from reddit-corpus!`)
