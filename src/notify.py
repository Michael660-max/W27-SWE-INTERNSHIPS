from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

from .config import DISCORD_WEBHOOK_URL, NOTIFICATIONS_DIR
from .db import record_notification
from .models import JobRecord
from .score import sort_jobs
from .urls import job_apply_url

DISCORD_MAX = 1900
LISTINGS_URL = (
    "https://github.com/Michael660-max/W27-SWE-INTERNSHIPS/blob/main/LISTINGS.md"
)


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


def build_discord_short(jobs: list[JobRecord], prefix: str = "") -> str:
    jobs = sort_jobs(jobs)
    lines = []
    if prefix:
        lines.append(prefix.rstrip())
    lines.append(f"**{len(jobs)} new internship role(s)** — see full table:")
    lines.append(LISTINGS_URL)
    lines.append("")
    for i, job in enumerate(jobs[:15], 1):
        apply = job_apply_url(job)
        src = (job.source_names or "").split(";")[0].strip() or "?"
        link = apply if apply else "no apply URL"
        lines.append(
            f"{i}. **{job.company}** — {job.exact_role_title} — {job.location or '?'} — "
            f"{job.term or '?'} — _{src}_ — {link}"
        )
    if len(jobs) > 15:
        lines.append(f"_…and {len(jobs) - 15} more in LISTINGS.md_")
    return "\n".join(lines)


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
        lines.append("")
        lines.append("| Company | Role | Location | Term | Posted | Link |")
        lines.append("|---|---|---|---|---|---|")
        for j in fresh:
            url = j.official_url or j.source_url or ""
            lines.append(
                f"| {j.company} | {j.exact_role_title} | {j.location} | {j.term} | "
                f"{_posting_short(j)} | {url} |"
            )
        lines.append("")
    if late:
        lines.append("## Late discovery")
        lines.append("")
        lines.append("| Company | Role | Location | Term | Posted | Link |")
        lines.append("|---|---|---|---|---|---|")
        for j in late:
            url = j.official_url or j.source_url or ""
            lines.append(
                f"| {j.company} | {j.exact_role_title} | {j.location} | {j.term} | "
                f"{_posting_short(j)} | {url} |"
            )
        lines.append("")
    if unavailable:
        lines.append("## Posting date unavailable")
        lines.append("")
        lines.append("| Company | Role | Location | Term | Posted | Link |")
        lines.append("|---|---|---|---|---|---|")
        for j in unavailable:
            url = j.official_url or j.source_url or ""
            lines.append(
                f"| {j.company} | {j.exact_role_title} | {j.location} | {j.term} | "
                f"{_posting_short(j)} | {url} |"
            )
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
) -> bool:
    webhook_url = (webhook_url if webhook_url is not None else DISCORD_WEBHOOK_URL).strip()
    if not jobs:
        return False
    if dry_run or not webhook_url:
        return False

    jobs = sort_jobs(jobs)
    chunks: list[str] = []

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
        msg = build_discord_short(jobs, prefix=prefix)
        # chunk if needed
        if len(msg) <= 2000:
            chunks = [msg]
        else:
            chunks = [msg[i : i + 1900] for i in range(0, len(msg), 1900)]

    if not chunks and prefix:
        chunks = [prefix]

    with httpx.Client(timeout=30.0) as client:
        for chunk in chunks:
            content = chunk if len(chunk) <= 2000 else chunk[:1990] + "\n…"
            resp = client.post(webhook_url, json={"content": content})
            resp.raise_for_status()
    return True


def notify_new_jobs(
    conn,
    jobs: list[JobRecord],
    dry_run: bool = False,
    prefix: str = "",
    style: str = "short",
) -> Path | None:
    if not jobs:
        return None
    path = write_notification_file(jobs)
    sent = send_discord(jobs, dry_run=dry_run, prefix=prefix, style=style)
    channel = "discord" if sent else ("dry_run" if dry_run else "file_only")
    for job in jobs:
        record_notification(
            conn,
            job.id,
            channel,
            {"markdown_path": str(path) if path else "", "title": job.exact_role_title},
        )
    return path
