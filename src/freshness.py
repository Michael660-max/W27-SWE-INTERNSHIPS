from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .config import FRESHNESS_BUFFER_HOURS, TIMEZONE


def toronto_now(now: datetime | None = None) -> datetime:
    tz = ZoneInfo(TIMEZONE)
    if now is None:
        return datetime.now(tz)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc).astimezone(tz)
    return now.astimezone(tz)


def previous_run_cutoff(now: datetime | None = None) -> datetime:
    """Return the start of the freshness window for the current run."""
    local = toronto_now(now)
    buffer = timedelta(hours=FRESHNESS_BUFFER_HOURS)

    midday = local.replace(hour=12, minute=30, second=0, microsecond=0)
    evening = local.replace(hour=18, minute=0, second=0, microsecond=0)

    # Determine which run we're in / closest to
    if local.hour < 12 or (local.hour == 12 and local.minute < 30):
        # Before midday → treat as evening-style lookback to prior midday? Prefer previous evening.
        # Actually: if running before 12:30, previous scheduled run was yesterday 18:00 (or Fri).
        prev = _previous_weekday_at(local, hour=18, minute=0)
    elif local < evening:
        # Midday run window: since previous 18:00
        prev = _previous_weekday_at(local, hour=18, minute=0, before=midday)
    else:
        # Evening run: since same-day 12:30
        prev = midday

    return prev - buffer


def _previous_weekday_at(
    local: datetime,
    hour: int,
    minute: int,
    before: datetime | None = None,
) -> datetime:
    """Most recent weekday occurrence of hour:minute strictly before `before` or `local`."""
    anchor = before or local
    candidate = anchor.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate >= anchor:
        candidate -= timedelta(days=1)
    # Skip weekends: if landing on Sat/Sun, go to Friday
    while candidate.weekday() >= 5:  # 5=Sat, 6=Sun
        candidate -= timedelta(days=1)
    # Monday midday should look back to Friday 18:00 — weekday() loop handles Sat/Sun
    return candidate


def label_freshness(
    posting_date: datetime | None,
    first_found_at: datetime,
    window_start: datetime,
) -> str:
    if posting_date is None:
        return "Posting date unavailable"
    # Normalize tz
    pd = posting_date if posting_date.tzinfo else posting_date.replace(tzinfo=timezone.utc)
    ws = window_start if window_start.tzinfo else window_start.replace(tzinfo=timezone.utc)
    ff = first_found_at if first_found_at.tzinfo else first_found_at.replace(tzinfo=timezone.utc)

    if pd >= ws:
        return "Fresh"
    # Older posting but newly discovered
    if ff >= ws:
        return "Late discovery"
    return "Late discovery"


def posting_sort_key(posting_date_iso: str | None) -> float:
    """Higher is newer; missing dates sort last (very small key)."""
    if not posting_date_iso:
        return float("-inf")
    try:
        dt = datetime.fromisoformat(posting_date_iso.replace("Z", "+00:00"))
        return dt.timestamp()
    except Exception:
        return float("-inf")


FRESHNESS_RANK = {
    "Fresh": 0,
    "Late discovery": 1,
    "Posting date unavailable": 2,
}
