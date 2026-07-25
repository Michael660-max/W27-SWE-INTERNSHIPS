from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import APPLIED_STATUSES, ROOT as PROJECT_ROOT  # noqa: E402
from src.db import all_jobs, connect, ensure_db, get_job_by_id, update_job, utc_now_iso  # noqa: E402
from src.score import job_is_competitive, sort_jobs  # noqa: E402
from src.urls import job_apply_url  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / "ui" / "static"

app = FastAPI(title="W27 Internship Tracker", docs_url="/docs")


class AppliedStatusUpdate(BaseModel):
    applied_status: str = Field(..., min_length=1)


def _job_to_dict(job) -> dict:
    return {
        "id": job.id,
        "company": job.company,
        "exact_role_title": job.exact_role_title,
        "normalized_role_type": job.normalized_role_type,
        "location": job.location,
        "country": job.country,
        "remote_or_hybrid": job.remote_or_hybrid,
        "term": job.term,
        "posting_date": job.posting_date,
        "posting_date_precision": job.posting_date_precision,
        "freshness_label": job.freshness_label,
        "priority_score": job.priority_score,
        "competitive_company": job_is_competitive(job),
        "official_url": job_apply_url(job) or job.official_url or job.source_url,
        "apply_url": job_apply_url(job),
        "status": job.status,
        "applied_status": job.applied_status,
        "requires_us_citizenship": bool(job.requires_us_citizenship),
        "requires_us_work_auth": bool(job.requires_us_work_auth),
        "requires_export_control": bool(job.requires_export_control),
        "eligibility_notes": job.eligibility_notes,
        "source_names": job.source_names,
        "first_found_at": job.first_found_at,
        "last_seen_at": job.last_seen_at,
        "agent_only": bool(job.agent_only),
        "notes": job.notes,
    }


@app.on_event("startup")
def _startup() -> None:
    ensure_db()


@app.get("/")
def index() -> FileResponse:
    path = STATIC_DIR / "index.html"
    if not path.exists():
        raise HTTPException(404, "UI not found")
    return FileResponse(path)


@app.get("/api/meta")
def meta() -> dict:
    return {
        "applied_statuses": list(APPLIED_STATUSES),
        "db_path": str(PROJECT_ROOT / "data" / "jobs.sqlite"),
    }


@app.get("/api/jobs")
def list_jobs(
    q: Optional[str] = Query(None, description="Search company/title/location/term"),
    freshness: Optional[str] = None,
    country: Optional[str] = None,
    remote: Optional[str] = None,
    status: Optional[str] = None,
    applied_status: Optional[str] = None,
    competitive: Optional[bool] = None,
) -> dict:
    ensure_db()
    with connect() as conn:
        jobs = sort_jobs(all_jobs(conn))

    q_norm = (q or "").strip().lower()
    filtered = []
    for job in jobs:
        if competitive is not None and job_is_competitive(job) != competitive:
            continue
        if freshness and (job.freshness_label or "") != freshness:
            continue
        if status and (job.status or "") != status:
            continue
        if applied_status and (job.applied_status or "") != applied_status:
            continue
        if remote and (job.remote_or_hybrid or "").lower() != remote.lower():
            continue
        if country:
            blob = f"{job.country or ''} {job.location or ''}".lower()
            key = country.lower()
            if key == "canada" and "canada" not in blob:
                continue
            if key in {"us", "united states"}:
                has_us = any(x in blob for x in ("united states", "usa", "u.s"))
                has_canada = "canada" in blob
                if has_canada and not has_us:
                    continue
        if q_norm:
            hay = " ".join(
                [
                    job.company or "",
                    job.exact_role_title or "",
                    job.location or "",
                    job.term or "",
                    job.source_names or "",
                ]
            ).lower()
            if q_norm not in hay:
                continue
        filtered.append(_job_to_dict(job))

    return {"count": len(filtered), "jobs": filtered}


@app.patch("/api/jobs/{job_id}")
def patch_job(job_id: int, body: AppliedStatusUpdate) -> dict:
    if body.applied_status not in APPLIED_STATUSES:
        raise HTTPException(
            400,
            f"Invalid applied_status. Allowed: {', '.join(APPLIED_STATUSES)}",
        )
    ensure_db()
    with connect() as conn:
        job = get_job_by_id(conn, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        job = update_job(
            conn,
            job_id,
            {
                "applied_status": body.applied_status,
                "last_seen_at": job.last_seen_at or utc_now_iso(),
            },
        )
        # application history
        conn.execute(
            "INSERT INTO application_status (job_id, status, changed_at, notes) VALUES (?, ?, ?, ?)",
            (job_id, body.applied_status, utc_now_iso(), "updated via UI"),
        )
    return _job_to_dict(job)


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
