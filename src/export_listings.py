from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .config import LISTINGS_PATH
from .db import all_jobs, connect
from .normalize import matches_listings_season
from .score import sort_jobs
from .urls import job_apply_url


def _md_cell(text: str) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ").strip()


def _posting(job) -> str:
    p = job.posting_date or ""
    if not p:
        return "n/a"
    return p.split("T")[0] if "T" in p else p


def is_winter_2027(job) -> bool:
    """Back-compat name; board uses the shared loose season matcher."""
    return matches_listings_season(job)


def export_listings(path: Path | None = None) -> Path:
    path = path or LISTINGS_PATH
    with connect() as conn:
        jobs = sort_jobs([j for j in all_jobs(conn) if matches_listings_season(j)])

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Winter / Spring 2027 Software Internships",
        "",
        f"_Auto-generated from `data/jobs.sqlite` at {generated}. "
        "Loose filter: **Winter / Spring / Jan / off-cycle 2027** (Spring = Jan-start winter term). "
        "Excludes summer-only and fall-2026-only. "
        "Re-run `python src/main.py --export-listings-only` to refresh._",
        "",
        f"**{len(jobs)} roles** matching Winter/Spring 2027. Sorted by freshness → posting date → priority.",
        "",
        "| Company | Role | Location | Term | Posted | Source | Apply |",
        "|---|---|---|---|---|---|---|",
    ]

    for job in jobs:
        apply = job_apply_url(job)
        apply_cell = f"[Apply]({apply})" if apply else "—"
        source = job.source_names or "—"
        # Prefer first/primary source for readability when many are merged
        if ";" in source:
            parts = [p.strip() for p in source.split(";") if p.strip()]
            source = parts[0] + (f" +{len(parts) - 1}" if len(parts) > 1 else "")
        lines.append(
            "| "
            + " | ".join(
                [
                    _md_cell(job.company),
                    _md_cell(job.exact_role_title),
                    _md_cell(job.location or "—"),
                    _md_cell(job.term or "—"),
                    _md_cell(_posting(job)),
                    _md_cell(source),
                    apply_cell,
                ]
            )
            + " |"
        )

    lines.append("")
    lines.append("## Legend")
    lines.append("")
    lines.append("- **Source** — where the tracker first/also saw the role (GitHub list, ATS, agent).")
    lines.append("- **Apply** — official/ATS application link when available; `—` means no reliable apply URL yet.")
    lines.append("- Browse interactively: `bash scripts/ui.sh` → http://127.0.0.1:8787")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path
