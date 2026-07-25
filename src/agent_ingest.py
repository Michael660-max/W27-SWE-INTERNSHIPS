from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from dateutil import parser as date_parser

from .config import AGENT_FINDINGS_DIR
from .models import CandidateJob
from .normalize import enrich_candidate, should_keep_candidate

logger = logging.getLogger(__name__)

SOURCE_NAME = "Cursor Agent Monitor"


def load_findings_files(directory: Path | None = None) -> list[Path]:
    directory = directory or AGENT_FINDINGS_DIR
    if not directory.exists():
        return []
    return sorted(
        p
        for p in directory.iterdir()
        if p.suffix.lower() == ".json"
        and p.name != ".gitkeep"
        and not p.name.endswith(".schema.json")
    )


def parse_finding_file(path: Path) -> list[CandidateJob]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items: list[Any]
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict) and "jobs" in data:
        items = data["jobs"]
    elif isinstance(data, dict) and "findings" in data:
        items = data["findings"]
    elif isinstance(data, dict):
        items = [data]
    else:
        logger.warning("Unrecognized findings format: %s", path)
        return []

    candidates: list[CandidateJob] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        cand = _item_to_candidate(item, path)
        if not cand:
            continue
        cand = enrich_candidate(cand)
        ok, reason = should_keep_candidate(cand)
        if not ok:
            logger.debug("Agent finding skipped (%s): %s", reason, cand.exact_role_title)
            continue
        candidates.append(cand)
    return candidates


def collect_agent_findings(directory: Path | None = None) -> list[CandidateJob]:
    files = load_findings_files(directory)
    all_c: list[CandidateJob] = []
    for path in files:
        try:
            all_c.extend(parse_finding_file(path))
        except Exception as exc:
            logger.warning("Failed to parse %s: %s", path, exc)
    logger.info("Agent findings: %d candidates from %d files", len(all_c), len(files))
    return all_c


def write_findings_template(path: Path, jobs: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": SOURCE_NAME,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "jobs": jobs,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _item_to_candidate(item: dict[str, Any], path: Path) -> CandidateJob | None:
    company = (item.get("company") or "").strip()
    title = (item.get("exact_role_title") or item.get("title") or item.get("role") or "").strip()
    if not company or not title:
        return None
    url = (
        item.get("official_url")
        or item.get("url")
        or item.get("apply_url")
        or item.get("link")
        or ""
    ).strip()
    posting_raw = item.get("posting_date") or item.get("posted_at")
    posting_date = None
    precision = "unknown"
    if posting_raw:
        try:
            posting_date = date_parser.parse(str(posting_raw))
            precision = "datetime" if "T" in str(posting_raw) else "date"
        except Exception:
            posting_date = None
    freshness = item.get("freshness_label") or ""
    notes = item.get("notes") or ""
    if freshness:
        notes = f"{notes}; freshness_hint={freshness}".strip("; ")
    competitive_raw = item.get("competitive")
    agent_competitive: bool | None = None
    if competitive_raw is not None:
        agent_competitive = bool(competitive_raw)

    return CandidateJob(
        company=company,
        exact_role_title=title,
        location=str(item.get("location") or ""),
        term=str(item.get("term") or item.get("dates") or ""),
        official_url=url,
        source_url=url,
        source_name=SOURCE_NAME,
        posting_date=posting_date,
        posting_date_precision=precision,
        eligibility_notes=str(item.get("eligibility_notes") or item.get("eligibility") or ""),
        requires_us_citizenship=bool(item.get("requires_us_citizenship")),
        requires_us_work_auth=bool(item.get("requires_us_work_auth")),
        requires_export_control=bool(item.get("requires_export_control")),
        raw_text_snapshot=json.dumps(item, ensure_ascii=False)[:15000],
        notes=f"from {path.name}" + (f"; {notes}" if notes else ""),
        agent_competitive=agent_competitive,
    )
