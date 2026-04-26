# Reddit Data API requires pre-approval (no self-serve credentials)

Status: Accepted
Date: 2026-04-26

## Context

Reddit's Responsible Builder Policy, rolled out late 2025, ended self-service
creation of new OAuth2 applications. The legacy `reddit.com/prefs/apps`
form is still live, but submissions for accounts that have not been pre-approved
silently fail — the page bounces back with an empty reCAPTCHA, no error message.
This is widely reported and is the *current* state of the world, not a transient
bug. Existing OAuth2 apps continue to work; only new app creation is gated.

For our purposes (a personal, longitudinal Reddit corpus, ≤ 100 QPM, single
account, no redistribution, no model training) the Responsible Builder Policy
explicitly preserves a free non-commercial tier — but access to it is now
behind manual review through Reddit's Developer Support form. Reddit's stated
SLA is ~7 days; community reports show it ranges from same-day to never.

## Decision

We continue to depend on Reddit's official Data API via `praw` (see ADR 0001
on the notebook stance — that decision is unchanged) and we will go through the
official application path rather than scraping HTML or using third-party
archives as the primary source.

Application path:

1. **Read the Responsible Builder Policy.**
   <https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy>
   It governs both *whether* we can use the API and *how* we describe ourselves
   in the application — describing the project as "training data" or "AI
   training" risks an automatic denial; describing it as "personal LLM-assisted
   research over a small set of subreddits, no redistribution" matches the
   permitted non-commercial tier.

2. **Apply via the Developer Support form.** Direct URL:
   <https://support.reddithelp.com/hc/en-us/requests/new?ticket_form_id=14868593862164>
   `ticket_form_id=14868593862164` is the API access request form specifically.
   The general hub page (<https://support.reddithelp.com/hc/en-us/articles/14945211791892-Developer-Platform-Accessing-Reddit-Data>)
   links to this same form — the direct URL above just skips the click.

   **The form will display a Devvit redirect notice** telling you to consider
   Devvit first. Ignore it for this project — Devvit is Reddit's *in-Reddit*
   app platform (subreddit-installable apps running on Reddit's infrastructure,
   visible inside the Reddit UI). It cannot write to a local SQLite file or
   run on a cron schedule under your user account, so it is architecturally
   wrong for a personal corpus tool. Address this head-on in the use-case
   description ("Not a Devvit fit: local Python script writing to local
   SQLite, offline LLM analysis — Devvit can't write to local storage") so
   the reviewer doesn't bounce the application back.

   The form asks for:
   - Use case (one paragraph)
   - Subreddits accessed
   - Data fetched (posts, comments, etc.)
   - Expected request volume (target: ≤ 100 QPM, well under any pricing tier)
   - Whether content is redistributed (no)
   - Whether content is used to train ML models (no)
   - Request type — pick **non-commercial** for personal projects under 100 QPM.

3. **Wait for the approval email** with the credentials. Once received, drop
   them into `config.toml` per README §Setup. The credentials work on every
   PC; this is a once-per-Reddit-account gate, not once-per-host.

## Fallback options if the application is denied or stalls

These are *not* equivalent to the official API and will require code changes
in `reddit/client.py` and `reddit/ingest.py` if adopted. Listed in declining
order of fidelity to the existing design:

- **Reuse a pre-policy refresh token** — any account that registered a script
  app before late 2025 retains working credentials. Check `~/.praw.ini`,
  password managers, and any old projects before assuming this is unavailable.
- **Arctic Shift / community Reddit archive APIs** — read-only, OAuth-free,
  bounded in completeness and freshness but adequate for "longitudinal
  notebook" semantics. Would replace `praw` entirely; the corpus schema
  (Slice 3) is unaffected because storage is shape-neutral.
- **Reddit RSS feeds** (`https://www.reddit.com/r/<sub>/.rss`) — no auth, no
  rate-limit-friendly headers, capped at 25 posts per feed, no comments
  without per-thread fetches. Workable for the very smallest cases; would
  require a different ingest layer.
- **`redlib` / `libreddit` HTML scraping** — explicitly violates Reddit ToS
  and the Notebook stance's spirit. Listed for completeness only; not a
  recommended path.

## Consequences

- **Plan assumption 1 (in `reddit-scraper-plan.md`) is no longer "API access
  remains available"; it's "API access remains available *to applicants
  approved through the post-2025 Responsible Builder process*."** That's a
  weaker assumption — flag-worthy but not project-killing for personal use.
- The first-run user experience now begins with a multi-day wait. The README
  reflects this: setup walks the user to the application form first, and the
  remaining steps cover what to do once credentials arrive.
- The `auth test` command's failure mode is the same as before (401 → README
  §Re-authenticating), but the README's troubleshooting now distinguishes
  "credentials expired" from "credentials never approved" because the
  symptoms look similar to a new user.
- **No code changes required.** PRAW continues to work the same way once
  credentials exist. The schema, config layer, CLI, and tests are unaffected.
