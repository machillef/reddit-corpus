# reddit-corpus

Personal Reddit corpus tool — a scheduled `praw` ingester paired with an LLM-friendly query CLI over a local SQLite store. Cross-platform (Windows / Linux / macOS).

> **Status: foundation built.** Slices 1–5 complete (CI, pre-flight, schema, config, auth). See `docs/ai/reddit-scraper-status.md` for the live slice tracker.

> **If you're reading this trying to remember how setup works**: jump straight to [Setup](#setup) — the OAuth bootstrap is steps 2–3. You only do those once per Reddit account, ever. Steps 1, 4, 5 are once per PC. **As of late 2025, step 2 requires Reddit's manual approval (~7-day wait) — see the heads-up box at the top of step 2 and `docs/adr/0002-reddit-api-pre-approval.md`.**

## Prerequisites

- **Python 3.13+** ([download](https://www.python.org/downloads/))
- **uv** (Python package manager) — install one-liner:
  - macOS / Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
  - Windows (PowerShell): `irm https://astral.sh/uv/install.ps1 | iex`
  - Or, if Python+pip already present: `pip install uv`

A pre-flight check script lives at `scripts/check_prereqs.py`. Run it before `uv sync` to verify the host has everything needed; it prints OS-specific install commands when something is missing.

```bash
# macOS / Linux
bash scripts/check-prereqs.sh

# Windows (PowerShell)
.\scripts\check-prereqs.ps1

# Or invoke the .py directly with any python3 interpreter
python3 scripts/check_prereqs.py
```

## Setup

This is a one-time bootstrap **per Reddit account**, not per machine. The Reddit
credentials you obtain below work everywhere — see [Multi-PC](#multi-pc) below.

### 1. Clone and sync

```bash
git clone <this-repo-url> reddit-corpus
cd reddit-corpus
uv sync                  # creates .venv, installs deps from uv.lock
```

### 2. Get Reddit API credentials (multi-day wait, late-2025 onward)

> **Heads up.** As of late 2025, Reddit gated self-service app creation behind
> the [Responsible Builder Policy](https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy).
> Submitting the form at `reddit.com/prefs/apps` for a new account silently
> fails (you get an "infinite captcha loop" — that's the symptom). New
> credentials must be obtained via Reddit's Developer Support form. Reddit's
> stated SLA is ~7 days. Existing pre-2025 credentials still work, so check
> `~/.praw.ini` and any old projects before applying. Background and fallback
> options: [`docs/adr/0002-reddit-api-pre-approval.md`](docs/adr/0002-reddit-api-pre-approval.md).

**Apply.** Direct URL to the Developer Support API-access form:

<https://support.reddithelp.com/hc/en-us/requests/new?ticket_form_id=14868593862164>

(Background: <https://support.reddithelp.com/hc/en-us/articles/14945211791892-Developer-Platform-Accessing-Reddit-Data> is the human-readable hub; the URL above is the form it links to. Pick **non-commercial** as the request type.)

> **Ignore the "go through Devvit first" notice on the form.** Devvit is Reddit's
> in-Reddit app platform (apps that run on Reddit's servers and render inside
> Reddit's UI for subreddits you moderate). It cannot write to a local SQLite
> file or run on a cron schedule on your machine, so it's architecturally
> wrong for a personal corpus tool. Pre-empt the reviewer's first question by
> adding one line at the top of the use-case description: *"Not a Devvit fit:
> local Python script writing to local SQLite for offline LLM analysis. Devvit
> apps run on Reddit's infrastructure and can't write to local storage."*

Suggested copy for the application (matches Reddit's permitted non-commercial
tier; describing the project as "ML training" or "AI training" risks an
automatic denial):

> Personal, single-user research notebook. I ingest posts and comment trees
> from a small set of subreddits (initially `r/anthropic`) into a local SQLite
> database, then query that database with an LLM-friendly CLI for my own
> longitudinal analysis. No redistribution of content. No model training.
> Read-only ingest, well under 100 QPM, runs once a day on a personal
> schedule. Open-source under a private repo.

Fields the form will ask for: use case, subreddits accessed, data fetched
(posts + comments), expected QPM (≤ 100), redistribution (no), model
training (no).

**Wait.** Reddit emails approval with credentials — `client_id` and
`client_secret`. The credentials are **account-scoped**, not host-scoped:
once you have them, they work on every PC.

While you wait: this repo's Slices 1–5 are runtime-complete against PRAW
fakes — `uv run pytest` still passes 86/86 — so you can keep refactoring or
plan Slice 6 without credentials. You only need real credentials to do a
live `auth test` and live ingest.

**Once approved, also confirm the redirect uri.** Reddit's email or developer
console will show your app's settings; the redirect uri must be
`http://localhost:8080` for the bootstrap below to work. If it's blank or set
to anything else, edit it.

### 3. Generate a refresh token (one-time, per Reddit account)

Save this snippet as `bootstrap_auth.py` anywhere outside the repo, fill in the
top three constants, and run with `uv run python bootstrap_auth.py`.

```python
import http.server, secrets, urllib.parse, webbrowser
import praw

CLIENT_ID     = "..."                                    # from step 2
CLIENT_SECRET = "..."                                    # from step 2
USER_AGENT    = "reddit-corpus/0.1 by u/yourhandle"      # any descriptive UA

reddit = praw.Reddit(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    redirect_uri="http://localhost:8080",
    user_agent=USER_AGENT,
)

state = secrets.token_urlsafe(16)
url = reddit.auth.url(
    scopes=["identity", "read", "history"],
    state=state,
    duration="permanent",                                # gives us a refresh token
)
print(f"\nOpen this URL in your browser if it doesn't open automatically:\n  {url}\n")
webbrowser.open(url)

class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if params.get("state", [""])[0] != state:
            self.send_response(400); self.end_headers()
            self.wfile.write(b"state mismatch"); return
        code = params.get("code", [None])[0]
        if not code:
            self.send_response(400); self.end_headers()
            self.wfile.write(b"no code"); return
        token = reddit.auth.authorize(code)
        print(f"\nrefresh_token: {token}\n")
        self.send_response(200); self.end_headers()
        self.wfile.write(b"OK. You can close this tab.")

    def log_message(self, *_):  # keep the terminal output clean
        pass

http.server.HTTPServer(("localhost", 8080), _Handler).handle_request()
```

A browser tab opens at Reddit's authorization page. Click **Allow**. The terminal
prints `refresh_token: ...` — copy it. **Save this token.** You will reuse it on
every PC.

### 4. Drop `config.toml` into the platform data dir

Copy `config.example.toml` from this repo to the platform data dir for `reddit-corpus`:

| OS | Path |
|----|------|
| Linux | `~/.local/share/reddit-corpus/config.toml` |
| macOS | `~/Library/Application Support/reddit-corpus/config.toml` |
| Windows | `%APPDATA%\reddit-corpus\reddit-corpus\config.toml` *(yes, the doubled `reddit-corpus` segment is `platformdirs`' Windows default)* |

Edit the file: replace `REPLACE_ME` for `client_id`, `client_secret`, `refresh_token`,
and `user_agent`. Leave `[paths] db_path = "default"`.

### 5. Verify

```bash
uv run reddit-corpus auth test
```

Expected: `OK — authenticated as u/<your-handle>` and exit 0.

### Multi-PC

Reddit credentials are **account-scoped, not host-scoped**. On every additional PC:

1. Clone this repo, run `uv sync`.
2. Copy your `config.toml` from the first PC into the new PC's platform data dir
   (paths in step 4). Same file, no changes needed.
3. `uv run reddit-corpus auth test` to confirm.

You do **not** redo steps 2 or 3 — those are once per Reddit account, ever, until
the token is revoked.

Alternative: skip the file entirely and set the four `REDDIT_CORPUS_*` env vars
in your shell profile. The CLI honors `REDDIT_CORPUS_CLIENT_ID`, `_CLIENT_SECRET`,
`_REFRESH_TOKEN`, `_USER_AGENT`, and `_DB`. Env wins over file.

## Re-authenticating

If `uv run reddit-corpus auth test` returns `received 401 HTTP response`, the
refresh token is no longer valid (or never was). Disambiguate first:

| Symptom | Likely cause |
|---|---|
| You never successfully created an app at `reddit.com/prefs/apps` (got the captcha loop) | **Credentials never approved.** Redo §Setup step 2 — file the developer support application and wait for approval. This is the post-2025 default for new Reddit accounts. |
| You used the credentials before and they worked, now they don't | Refresh token expired, secret rotated, or app revoked. Redo §Setup step 3 with the same client_id / client_secret if those are still valid. |
| `auth test` says `Missing required Reddit credentials` (not 401) | `config.toml` is missing or unreadable — check the platform data dir path in §Setup step 4. |

To recover from a 401 with credentials that previously worked:

1. Visit [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) — confirm the
   app still exists in the list.
2. If the script app is gone, redo §Setup step 2 (apply for new credentials).
3. If the secret was rotated, paste the new secret into `config.toml`.
4. If only the refresh token is stale, redo §Setup step 3 only (the client_id /
   client_secret stay the same — you just need a fresh refresh token). Save the
   new token; copy it to every PC's `config.toml`.

## Usage (planned — Slice 6+ pending)

```bash
# Ingest top + new posts (with full comment trees) from configured subreddits
uv run reddit-corpus ingest

# LLM-facing queries (markdown by default; --format json for pipelines)
uv run reddit-corpus posts list --sub anthropic --since 7d
uv run reddit-corpus thread show <post_id>
uv run reddit-corpus comments search --sub anthropic --pattern "claude code"
uv run reddit-corpus subs list
```

Currently only `auth test` is wired (Slice 5). The other commands land in Slices 6–10.

## Development

```bash
uv run pytest                     # all tests
uv run pytest tests/path/test.py  # single file or single test
uv run ruff check .               # lint
uv run ruff format .              # format
uv run ty check                   # type-check (beta)
```

CI runs the quality gates on Windows / Linux / macOS.

## Documentation

- `docs/ai/reddit-scraper-requirements.md` — what we're building, scale, constraints, non-goals
- `docs/ai/reddit-scraper-design.md` — approved architecture (layers, data flow, schema, CLI surface)
- `docs/ai/reddit-scraper-decisions.md` — stack decisions and rationale
- `docs/ai/reddit-scraper-status.md` — initiative state and slice progress

## License

TBD (private repo).
