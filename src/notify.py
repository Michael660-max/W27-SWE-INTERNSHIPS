from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

from .config import NOTIFICATIONS_DIR, TIMEZONE
from . import config
from .db import all_jobs, last_digest_at, record_digest, record_notification
from .models import JobRecord
from .score import sort_jobs
from .urls import is_apply_url, job_apply_url

DISCORD_MAX = 1900
LISTINGS_URL = (
    "https://github.com/Michael660-max/W27-SWE-INTERNSHIPS/blob/main/LISTINGS.md"
)

# Statuses that may be Discord-alerted (new inserts only; see filter_notifiable_jobs).
NOTIFIABLE_STATUSES = frozenset({"Open"})


def filter_notifiable_jobs(jobs: list[JobRecord]) -> list[JobRecord]:
    """
    Only newly inserted *valid* roles: Open status + real apply URL.
    Unverified / Closed / homepage-only links are skipped for Discord + notify files.
    """
    out: list[JobRecord] = []
    for job in jobs:
        if (job.status or "") not in NOTIFIABLE_STATUSES:
            continue
        apply = job_apply_url(job)
        if not apply or not is_apply_url(apply):
            continue
        out.append(job)
    return sort_jobs(out)


def _posting_short(job: JobRecord) -> str:
    posting = job.posting_date or "n/a"
    if posting and "T" in posting:
        posting = posting.split("T")[0]
    return posting


def _eligibility_flags(job: JobRecord) -> str:
    flags = []
    if job.requires_us_citizenship:
        flags.append("🇺🇸")
    if job.requires_us_work_auth:
        flags.append("🛂")
    if job.requires_export_control:
        flags.append("🔒")
    if job.agent_only:
        flags.append("🤖")
    return "".join(flags)


def format_job_line(job: JobRecord, include_freshness_label: bool = True) -> str:
    posting = _posting_short(job)
    parts = []
    if include_freshness_label and job.freshness_label:
        parts.append(f"[{job.freshness_label}]")
    parts.extend(
        [
            job.company or "Unknown",
            "-",
            job.exact_role_title or "Unknown role",
            "-",
            job.location or "Location n/a",
            "-",
            job.term or "Term n/a",
            "-",
            posting,
            "-",
            job.official_url or job.source_url or "(no link)",
        ]
    )
    line = " ".join(parts)
    flags = []
    if job.requires_us_citizenship:
        flags.append("U.S. citizenship required")
    if job.requires_us_work_auth:
        flags.append("U.S. work authorization required")
    if job.requires_export_control:
        flags.append("Export-control eligibility required")
    if job.agent_only:
        flags.append("Agent-only discovery")
    if flags:
        line += "\n   " + " | ".join(flags)
    return line


def _clip(text: str, width: int) -> str:
    text = (text or "").replace("\n", " ").strip()
    if len(text) <= width:
        return text
    if width <= 1:
        return text[:width]
    return text[: width - 1] + "…"


def build_simplify_style_table(jobs: list[JobRecord], title: str) -> str:
    """
    Monospace table resembling Simplify GitHub list columns.
    Discord doesn't render markdown tables; code fences preserve alignment.
    """
    jobs = sort_jobs(jobs)
    cols = [
        ("Company", 14, lambda j: j.company or ""),
        ("Role", 24, lambda j: j.exact_role_title or ""),
        ("Location", 14, lambda j: j.location or ""),
        ("Term", 14, lambda j: j.term or ""),
        ("Source", 16, lambda j: (j.source_names or "").split(";")[0].strip()),
        ("Posted", 10, lambda j: _posting_short(j)),
        ("Flags", 4, _eligibility_flags),
    ]
    header = " | ".join(_clip(name, w).ljust(w) for name, w, _ in cols)
    sep = "-+-".join("-" * w for _, w, _ in cols)
    rows = [header, sep]
    for job in jobs:
        rows.append(" | ".join(_clip(fn(job), w).ljust(w) for _, w, fn in cols))

    links = []
    for i, job in enumerate(jobs, 1):
        url = job_apply_url(job)
        if url:
            links.append(f"{i}. {job.company} — {url}")
        else:
            links.append(f"{i}. {job.company} — (no apply URL)")

    body = "\n".join(rows)
    out = f"**{title}** ({len(jobs)})\n```\n{body}\n```"
    if links:
        out += "\n**Apply:**\n" + "\n".join(links)
    out += f"\nFull board: {LISTINGS_URL}"
    out += "\n_Flags: 🇺🇸 citizenship · 🛂 work auth · 🔒 export · 🤖 agent-only_"
    return out


_TIER_ORDER = (
    ("apply_now", "Apply now"),
    ("good_lead", "Good lead"),
    ("late_discovery", "Late discovery"),
    ("needs_manual_verification", "Needs manual verification"),
)


def _tier_of(job: JobRecord) -> str:
    t = (getattr(job, "alert_tier", None) or "").strip()
    if t:
        return t
    if (job.freshness_label or "") == "Late discovery":
        return "late_discovery"
    if (job.status or "") == "Unverified":
        return "needs_manual_verification"
    if (job.freshness_label or "") == "Fresh":
        return "good_lead"
    return "good_lead"


def mention_prefix() -> str:
    """`<@USER_ID>` so the evening digest pings you (needs DISCORD_USER_ID)."""
    uid = (config.DISCORD_USER_ID or "").strip()
    if uid.isdigit():
        return f"<@{uid}>"
    return ""


def build_discord_short(jobs: list[JobRecord], prefix: str = "") -> str:
    """Summary Discord: counts by alert tier + LISTINGS link."""
    jobs = sort_jobs(jobs)
    n = len(jobs)
    lines = []
    if prefix:
        lines.append(prefix.rstrip())
    noun = "role" if n == 1 else "roles"
    lines.append(f"**W27 daily digest:** {n} new {noun} since last evening summary.")
    for key, label in _TIER_ORDER:
        count = sum(1 for j in jobs if _tier_of(j) == key)
        if count:
            lines.append(f"• {label}: {count}")
    if n == 0:
        lines.append("_No new Open roles with apply links — scout still ran._")
    lines.append(f"Full board: {LISTINGS_URL}")
    return "\n".join(lines)


def build_notification_markdown(jobs: list[JobRecord]) -> str:
    jobs = sort_jobs(jobs)
    lines = [
        f"# New internship roles — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "_`first_found_at` is the reliable system timestamp; `Posted` is employer/list age (helpful, not always trustworthy)._",
        "",
    ]
    any_section = False
    for key, label in _TIER_ORDER:
        group = [j for j in jobs if _tier_of(j) == key]
        if not group:
            continue
        any_section = True
        lines.append(f"## {label}")
        lines.append("")
        lines.append("| Company | Role | Location | Term | Posted | First seen | Link |")
        lines.append("|---|---|---|---|---|---|---|")
        for j in group:
            url = job_apply_url(j) or j.official_url or j.source_url or ""
            first = (j.first_found_at or "")[:10]
            lines.append(
                f"| {j.company} | {j.exact_role_title} | {j.location} | {j.term} | "
                f"{_posting_short(j)} | {first} | {url} |"
            )
        lines.append("")
    if not any_section:
        lines.append("_No new roles._")
    return "\n".join(lines).rstrip() + "\n"


def write_notification_file(jobs: list[JobRecord], directory: Path | None = None) -> Path | None:
    if not jobs:
        return None
    directory = directory or NOTIFICATIONS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = directory / f"{ts}.md"
    path.write_text(build_notification_markdown(jobs), encoding="utf-8")
    return path


def _chunk_table_message(title: str, jobs: list[JobRecord], prefix: str = "") -> list[str]:
    """Split jobs into Discord-sized table messages."""
    if not jobs:
        return []
    chunks: list[str] = []
    batch: list[JobRecord] = []
    for job in jobs:
        trial = batch + [job]
        msg = ""
        if prefix and not chunks:
            msg = prefix.rstrip() + "\n"
        msg += build_simplify_style_table(trial, title)
        if len(msg) > DISCORD_MAX and batch:
            head = prefix if (prefix and not chunks) else ""
            chunks.append(
                (head.rstrip() + "\n" if head else "") + build_simplify_style_table(batch, title)
            )
            batch = [job]
            prefix = ""  # only on first chunk
        else:
            batch = trial
    if batch:
        head = prefix if (prefix and not chunks) else ""
        chunks.append(
            (head.rstrip() + "\n" if head else "") + build_simplify_style_table(batch, title)
        )
    return chunks


def send_discord(
    jobs: list[JobRecord],
    webhook_url: str | None = None,
    dry_run: bool = False,
    prefix: str = "",
    style: str = "short",
    *,
    allow_empty: bool = False,
    mention: bool = False,
) -> bool:
    webhook_url = (webhook_url if webhook_url is not None else config.DISCORD_WEBHOOK_URL).strip()
    if not jobs and not allow_empty:
        return False
    if dry_run or not webhook_url:
        return False

    jobs = sort_jobs(jobs) if jobs else []
    chunks: list[str] = []
    mention_line = mention_prefix() if mention else ""

    if style == "table":
        sections = [
            ("Fresh roles", [j for j in jobs if j.freshness_label == "Fresh"]),
            ("Late discovery", [j for j in jobs if j.freshness_label == "Late discovery"]),
            (
                "Posting date unavailable",
                [j for j in jobs if j.freshness_label == "Posting date unavailable"],
            ),
        ]
        first = True
        for title, items in sections:
            if not items:
                continue
            p = prefix if first else ""
            chunks.extend(_chunk_table_message(title, items, prefix=p))
            first = False
    else:
        head = "\n".join(x for x in [mention_line, prefix] if x)
        msg = build_discord_short(jobs, prefix=head)
        if len(msg) <= 2000:
            chunks = [msg]
        else:
            chunks = [msg[i : i + 1900] for i in range(0, len(msg), 1900)]

    if not chunks and prefix:
        chunks = [prefix]
    if not chunks and allow_empty:
        head = "\n".join(x for x in [mention_line, prefix] if x)
        chunks = [build_discord_short([], prefix=head)]

    payload_extra: dict = {}
    uid = (config.DISCORD_USER_ID or "").strip()
    if mention and uid.isdigit():
        payload_extra["allowed_mentions"] = {"users": [uid]}

    with httpx.Client(timeout=30.0) as client:
        for chunk in chunks:
            content = chunk if len(chunk) <= 2000 else chunk[:1990] + "\n…"
            body = {"content": content, **payload_extra}
            resp = client.post(webhook_url, json=body)
            resp.raise_for_status()
    return True


def notify_new_jobs(
    conn,
    jobs: list[JobRecord],
    dry_run: bool = False,
    prefix: str = "",
    style: str = "short",
    *,
    only_valid: bool = True,
    send: bool = False,
    mention: bool = False,
    allow_empty: bool = False,
    channel: str = "file_only",
) -> Path | None:
    """
    Write notification markdown. Discord send is opt-in (evening digest only).
    Pipeline inserts must not auto-post to Discord.
    """
    if only_valid:
        jobs = filter_notifiable_jobs(jobs)
    else:
        jobs = sort_jobs(jobs)
    if not jobs and not allow_empty:
        return None
    path = write_notification_file(jobs) if jobs else None
    sent = False
    if send:
        sent = send_discord(
            jobs,
            dry_run=dry_run,
            prefix=prefix,
            style=style,
            allow_empty=allow_empty,
            mention=mention,
        )
    ch = "discord_digest" if sent and channel == "discord_digest" else (
        "discord" if sent else ("dry_run" if dry_run else "file_only")
    )
    if jobs:
        for job in jobs:
            record_notification(
                conn,
                job.id,
                ch,
                {"markdown_path": str(path) if path else "", "title": job.exact_role_title},
            )
    elif sent:
        # Digest with zero jobs — still record a marker row on job_id 0 via notifications
        # using a dummy: store on notifications with job_id nullable? schema requires job_id.
        # Use payload-only via job_id=-1 not allowed. Skip per-job; coverage is enough.
        pass
    return path


def _parse_iso(value: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def digest_cutoff(conn) -> datetime:
    """Jobs first_found_at since last evening digest, else start of today America/Toronto."""
    from zoneinfo import ZoneInfo

    last = last_digest_at(conn)
    if last:
        dt = _parse_iso(last)
        if dt:
            return dt

    tz = ZoneInfo(TIMEZONE)
    local = datetime.now(tz)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(timezone.utc)


def jobs_for_daily_digest(conn) -> tuple[list[JobRecord], datetime]:
    cutoff = digest_cutoff(conn)
    cutoff_iso = cutoff.replace(microsecond=0).isoformat()
    jobs = []
    for job in all_jobs(conn):
        ff = job.first_found_at or ""
        if ff < cutoff_iso:
            continue
        jobs.append(job)
    return filter_notifiable_jobs(jobs), cutoff


def send_daily_digest(conn, dry_run: bool = False) -> Path | None:
    """
    Evening-only Discord: aggregate new Open+apply roles since last digest, @mention user.
    Returns the markdown path (if any). Raises RuntimeError if live digest cannot POST
    because DISCORD_WEBHOOK_URL is unset (so Automations fail loudly).
    """
    import logging

    logger = logging.getLogger(__name__)
    jobs, cutoff = jobs_for_daily_digest(conn)
    prefix = f"_Since {cutoff.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_"
    webhook = (config.DISCORD_WEBHOOK_URL or "").strip()

    if dry_run:
        mode = "dry_run"
    elif not webhook:
        mode = "missing_webhook"
        logger.error(
            "DISCORD_WEBHOOK_URL is unset — wrote digest file only; Discord was NOT sent. "
            "Add the webhook as a Cloud Agent secret on the Evening Automation."
        )
    else:
        mode = "live"

    path = notify_new_jobs(
        conn,
        jobs,
        dry_run=dry_run,
        prefix=prefix,
        style="short",
        only_valid=False,  # already filtered
        send=bool(webhook) and not dry_run,
        mention=True,
        allow_empty=True,
        channel="discord_digest",
    )
    record_digest(
        conn,
        job_count=len(jobs),
        mode=mode,
        notes="evening_daily_digest",
    )
    if mode == "missing_webhook":
        raise RuntimeError(
            "Evening digest not posted: set DISCORD_WEBHOOK_URL (and DISCORD_USER_ID) "
            "as Cloud Agent secrets, then re-run --daily-digest."
        )
    if webhook and not dry_run and not mention_prefix():
        logger.warning(
            "DISCORD_USER_ID unset or not numeric — digest posted without @mention"
        )
    return path
