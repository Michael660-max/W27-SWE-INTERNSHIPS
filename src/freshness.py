from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import sqlite3

from .config import FRESHNESS_BUFFER_HOURS, TIMEZONE
from .db import last_finished_run_at

TORONTO = ZoneInfo(TIMEZONE)
FRESHNESS_BUFFER = timedelta(hours=FRESHNESS_BUFFER_HOURS)

FRESHNESS_RANK = {
    "Fresh": 0,
    "Late discovery": 1,
    "Posting date unavailable": 2,
}


def toronto_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(TORONTO)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc).astimezone(TORONTO)
    return now.astimezone(TORONTO)


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
    while candidate.weekday() >= 5:  # 5=Sat, 6=Sun
        candidate -= timedelta(days=1)
    return candidate


def schedule_fallback_cutoff(now: datetime | None = None) -> datetime:
    """When no prior run exists, use the previous midday/evening scout slot (minus buffer applied by caller)."""
    local = toronto_now(now)
    midday = local.replace(hour=12, minute=30, second=0, microsecond=0)
    evening = local.replace(hour=18, minute=0, second=0, microsecond=0)

    if local.hour < 12 or (local.hour == 12 and local.minute < 30):
        prev = _previous_weekday_at(local, hour=18, minute=0)
    elif local < evening:
        prev = _previous_weekday_at(local, hour=18, minute=0, before=midday)
    else:
        prev = midday
    return prev


def previous_run_cutoff(now: datetime | None = None) -> datetime:
    """Schedule-only cutoff including buffer (legacy helper)."""
    return schedule_fallback_cutoff(now) - FRESHNESS_BUFFER


def _parse_iso(value: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def window_start_for_run(
    conn: sqlite3.Connection | None = None,
    now: datetime | None = None,
    *,
    buffer: timedelta = FRESHNESS_BUFFER,
) -> datetime:
    """
    Prefer last finished pipeline run (live or dry_run), minus buffer.
    Fall back to schedule slots when no runs are recorded yet.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    last_iso: str | None = None
    if conn is not None:
        last_iso = last_finished_run_at(conn)

    if last_iso:
        last_dt = _parse_iso(last_iso)
        if last_dt is not None:
            return last_dt - buffer

    return schedule_fallback_cutoff(now) - buffer


def label_freshness(
    posting_date: datetime | None,
    now: datetime | None = None,
    window_start: datetime | None = None,
    first_found_at: datetime | None = None,
) -> str:
    """
    Fresh vs Late uses employer posting_date when known (helpful, not always trustworthy).
    first_found_at is the reliable system clock — used when posting_date is missing:
    if we first saw it inside the window, treat as Late discovery (new to us, unknown age).
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if window_start is None:
        window_start = window_start_for_run(None, now)

    if posting_date is None:
        if first_found_at is not None:
            ff = first_found_at
            if ff.tzinfo is None:
                ff = ff.replace(tzinfo=timezone.utc)
            if ff >= window_start:
                return "Late discovery"
        return "Posting date unavailable"

    pd = posting_date
    if pd.tzinfo is None:
        pd = pd.replace(tzinfo=timezone.utc)

    if pd >= window_start:
        return "Fresh"
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
