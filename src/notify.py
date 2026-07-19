from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

from .config import DISCORD_WEBHOOK_URL, NOTIFICATIONS_DIR
from .db import record_notification
from .models import JobRecord
from .score import sort_jobs


def format_job_line(job: JobRecord, include_freshness_label: bool = True) -> str:
    posting = job.posting_date or "Posting date unavailable"
    # Prefer date-only display when ISO
    if posting and "T" in posting:
        posting = posting.split("T")[0]
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


def build_notification_markdown(jobs: list[JobRecord]) -> str:
    jobs = sort_jobs(jobs)
    fresh = [j for j in jobs if j.freshness_label == "Fresh"]
    late = [j for j in jobs if j.freshness_label == "Late discovery"]
    unavailable = [j for j in jobs if j.freshness_label == "Posting date unavailable"]

    lines = [
        f"# New internship roles — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ]
    if fresh:
        lines.append("## Fresh roles")
        for i, j in enumerate(fresh, 1):
            lines.append(f"{i}. {format_job_line(j, include_freshness_label=True)}")
        lines.append("")
    if late:
        lines.append("## Late discovery")
        for i, j in enumerate(late, 1):
            lines.append(f"{i}. {format_job_line(j, include_freshness_label=False)}")
        lines.append("")
    if unavailable:
        lines.append("## Posting date unavailable")
        for i, j in enumerate(unavailable, 1):
            lines.append(f"{i}. {format_job_line(j, include_freshness_label=True)}")
        lines.append("")
    if not jobs:
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


def send_discord(jobs: list[JobRecord], webhook_url: str | None = None, dry_run: bool = False) -> bool:
    webhook_url = (webhook_url if webhook_url is not None else DISCORD_WEBHOOK_URL).strip()
    if not jobs:
        return False
    if dry_run or not webhook_url:
        return False

    jobs = sort_jobs(jobs)
    # Discord 2000 char limit — chunk messages
    chunks: list[str] = []
    header_fresh = "**Fresh roles:**\n"
    header_late = "**Late discovery:**\n"
    header_unk = "**Posting date unavailable:**\n"

    def add_section(header: str, items: list[JobRecord], with_label: bool) -> None:
        if not items:
            return
        buf = header
        for i, j in enumerate(items, 1):
            line = f"{i}. {format_job_line(j, include_freshness_label=with_label)}\n"
            if len(buf) + len(line) > 1900:
                chunks.append(buf)
                buf = header + line
            else:
                buf += line
        chunks.append(buf)

    add_section(header_fresh, [j for j in jobs if j.freshness_label == "Fresh"], True)
    add_section(header_late, [j for j in jobs if j.freshness_label == "Late discovery"], False)
    add_section(
        header_unk,
        [j for j in jobs if j.freshness_label == "Posting date unavailable"],
        True,
    )

    with httpx.Client(timeout=30.0) as client:
        for chunk in chunks:
            resp = client.post(webhook_url, json={"content": chunk})
            resp.raise_for_status()
    return True


def notify_new_jobs(conn, jobs: list[JobRecord], dry_run: bool = False) -> Path | None:
    if not jobs:
        return None
    path = write_notification_file(jobs)
    sent = send_discord(jobs, dry_run=dry_run)
    channel = "discord" if sent else ("dry_run" if dry_run else "file_only")
    for job in jobs:
        record_notification(
            conn,
            job.id,
            channel,
            {"markdown_path": str(path) if path else "", "title": job.exact_role_title},
        )
    return path
