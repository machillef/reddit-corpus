# Requirements: reddit-scraper

## What we're building

A personal Reddit corpus tool with two cooperating parts:

1. **Ingester** — A scheduled Python program that uses Reddit's official API (via `praw`) to pull posts and full comment trees from a configurable list of subreddits. Honors Reddit's OAuth rate limits (100 QPM authenticated). Writes to a local SQLite database with a stable, deduplicating schema so data accumulates as a longitudinal corpus over weeks and months.

2. **Analysis CLI** — A thin command-line interface designed to be invoked by an LLM (Claude, primarily). Exposes ergonomic, structured queries over the SQLite corpus — e.g., "list top posts in /r/X for the last week", "fetch full thread for post Y", "search comments matching pattern Z". Output is shaped for LLM consumption (deterministic, parseable, with stable identifiers), so the LLM spends tokens on synthesis rather than fetching.

The two parts share the same SQLite store and schema. The ingester writes; the CLI reads.

## Scale and lifetime

- **Personal** use. Single user, no multi-tenancy, no auth surface beyond Reddit OAuth.
- **Longitudinal** — designed to accumulate data over months/years on a small set of subreddits. Not a high-throughput crawler.
- **Long-lived** — schema and CLI shapes should be stable enough that historical data remains queryable as the codebase evolves.

## Constraints

- **Cross-platform.** Must run unchanged on Windows 11, Linux, and macOS from a single codebase. No platform-specific paths, no hardcoded shell calls, no scheduler-specific glue. The user will register the ingester with their own scheduler (Task Scheduler / cron / launchd / systemd) on each host.
- **Source of truth: private GitHub repo.** Cloned to multiple machines. Code must be portable; runtime artifacts (the SQLite file, OAuth secrets, logs) must be excluded from version control.
- **Reddit official API only.** No HTML scraping fallback. Use `praw` so rate limiting, pagination, and auth are handled by a well-maintained library rather than reimplemented.
- **Pre-approved Reddit credentials required (post-2025 Responsible Builder Policy).** Self-service app creation at `reddit.com/prefs/apps` is gated as of late 2025 — credentials must be obtained via Reddit's Developer Support form (~7-day target turnaround). Once granted, the credentials work on every host (account-scoped, not host-scoped). See `docs/adr/0002-reddit-api-pre-approval.md` for the application path and fallback options if denied.
- **Rate-limit honoring is non-negotiable.** The ingester must never exceed Reddit's free OAuth limit (100 QPM) and should back off gracefully on `429` or `X-Ratelimit-Remaining: 0`.
- **Secrets stay out of code.** Reddit `client_id`, `client_secret`, `username`/`password` (or refresh token) live in a local config file or environment variables that are gitignored.
- **Subreddit selection** must be ergonomic: configurable via a top-of-file constant or config file *and* overridable via CLI arguments. Initial test target: `r/anthropic`.

## Team ecosystem

- **Python.** Aligns with the user's global preferences (`uv` for deps, `ruff` for lint/format, `ty` for type-checking, `pytest` for tests). Also the canonical ecosystem for Reddit work — `praw` is the de facto wrapper and has been maintained for over a decade.
- Target Python 3.12+.
- SQLite via the stdlib `sqlite3` module (no ORM dependency in v1 — schema is small and stability matters more than ergonomics).

## Non-goals

- **Not a public service.** No web UI, no API surface, no deployment story. Anything network-facing is out of scope.
- **No redistribution of collected content.** Content stays on the user's local SQLite. This keeps the project on the safe side of Reddit's Public Content Policy (personal/research use is tolerated; redistribution is not).
- **Not training data infrastructure.** No fine-tuning loops, no embedding pipelines, no vector DB in v1. The CLI hands raw structured text to the LLM at query time.
- **Not real-time.** Cron-cadence ingestion only. No streaming, no websockets, no live notifications.
- **No deployment automation.** The user is responsible for installing Python and registering the schedule on each host. Bootstrap should make it *easy* to do this manually, not automate it.
- **No multi-user support.** Single Reddit account, single corpus, single user.
- **No automatic schema migrations in v1.** If the schema needs to evolve, an explicit migration step (or a documented "drop and rebuild") is acceptable for personal-scale data.
