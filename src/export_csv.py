from __future__ import annotations

import csv
from pathlib import Path

from .config import CSV_PATH
from .db import all_jobs, connect
from .score import sort_jobs

CSV_FIELDS = [
    "id",
    "freshness_label",
    "posting_date",
    "posting_date_precision",
    "priority_score",
    "company",
    "exact_role_title",
    "normalized_role_type",
    "location",
    "country",
    "remote_or_hybrid",
    "term",
    "official_url",
    "canonical_url",
    "requisition_id",
    "ats_platform",
    "source_names",
    "status",
    "applied_status",
    "requires_us_citizenship",
    "requires_us_work_auth",
    "requires_export_control",
    "eligibility_notes",
    "first_found_at",
    "last_seen_at",
    "agent_only",
    "application_deadline",
    "notes",
]


def export_csv(path: Path | None = None) -> Path:
    path = path or CSV_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        jobs = sort_jobs(all_jobs(conn))
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for job in jobs:
            row = {k: getattr(job, k, "") for k in CSV_FIELDS}
            writer.writerow(row)
    return path
