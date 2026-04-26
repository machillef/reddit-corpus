"""PRAW rate-limit observation.

`observe(client)` reads PRAW's exposed `client.auth.limits` dict. PRAW manages
its own backoff before the cap; this module provides a single point of truth
for the ingest loop to defensively abort the next subreddit when the budget
gets too thin.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RateLimitState:
    remaining: float | None
    used: float | None
    reset_timestamp: float | None


def observe(client: Any) -> RateLimitState:
    """Read rate-limit fields from `client.auth.limits` if present.

    Returns a state with `None` fields when PRAW hasn't yet seen a request,
    rather than raising — the ingest loop treats unknown state as "no abort".
    """
    limits: dict[str, Any] = getattr(getattr(client, "auth", None), "limits", {}) or {}

    def _coerce(v: Any) -> float | None:
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    return RateLimitState(
        remaining=_coerce(limits.get("remaining")),
        used=_coerce(limits.get("used")),
        reset_timestamp=_coerce(limits.get("reset_timestamp")),
    )


def should_pause(state: RateLimitState, threshold: int = 10) -> bool:
    """True iff `remaining` is known and below `threshold`."""
    if state.remaining is None:
        return False
    return state.remaining < threshold
