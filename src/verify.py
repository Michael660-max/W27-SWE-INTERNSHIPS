from __future__ import annotations

import sqlite3
from urllib.parse import urlparse

from .db import update_job
from .http_util import get_client, head_or_get_ok
from .models import CandidateJob, JobRecord
from .normalize import matches_target_term


AGGREGATOR_HOSTS = {
    "simplify.jobs",
    "www.simplify.jobs",
    "linkedin.com",
    "www.linkedin.com",
    "indeed.com",
    "www.indeed.com",
    "levels.fyi",
    "www.levels.fyi",
    "dreamworkhq.com",
    "www.dreamworkhq.com",
}


def is_aggregator_url(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return False
    return host in AGGREGATOR_HOSTS or host.endswith(".simplify.jobs")


def prefer_official_url(candidate: CandidateJob) -> CandidateJob:
    """If source_url looks more official than official_url, swap."""
    official = candidate.official_url or ""
    source = candidate.source_url or ""
    if official and not is_aggregator_url(official):
        return candidate
    if source and not is_aggregator_url(source):
        candidate.official_url = source
    return candidate


def verify_candidate(candidate: CandidateJob, client=None) -> CandidateJob:
    candidate = prefer_official_url(candidate)
    url = candidate.official_url or candidate.source_url
    if not url:
        candidate.notes = _append_note(candidate.notes, "No URL to verify")
        return candidate

    if is_aggregator_url(url):
        candidate.notes = _append_note(candidate.notes, "Aggregator URL only")
        return candidate

    ok, status, final_url = head_or_get_ok(url, client=client)
    if final_url and final_url != url and not is_aggregator_url(final_url):
        candidate.official_url = final_url
    if not ok:
        candidate.notes = _append_note(
            candidate.notes, f"Official verification failed (HTTP {status})"
        )
    return candidate


def _looks_like_job_url(url: str) -> bool:
    low = (url or "").lower()
    if not low:
        return False
    if "github.com/" in low and "/blob/" in low:
        return False
    markers = (
        "/job",
        "/jobs",
        "gh_jid=",
        "greenhouse",
        "lever.co",
        "ashby",
        "workday",
        "rippling",
        "smartrecruiters",
        "icims",
        "simplify.jobs/p/",
    )
    return any(m in low for m in markers)


def verify_and_update_jobs(conn: sqlite3.Connection, jobs: list[JobRecord]) -> list[JobRecord]:
    updated: list[JobRecord] = []
    with get_client() as client:
        for job in jobs:
            url = job.official_url or job.source_url
            if not url or is_aggregator_url(url) or not _looks_like_job_url(url):
                job = update_job(conn, job.id, {"status": "Unverified"})
                updated.append(job)
                continue
            ok, status, final_url = head_or_get_ok(url, client=client)
            fields: dict = {}
            if final_url and final_url != url:
                fields["official_url"] = final_url
            if not ok:
                fields["status"] = "Unverified"
                fields["notes"] = _append_note(job.notes, f"Verification failed HTTP {status}")
            else:
                # Confirm term still plausible from stored snapshot
                blob = f"{job.exact_role_title} {job.term} {job.raw_text_snapshot}"
                if job.term and not matches_target_term(blob) and "2027" not in (job.term or ""):
                    fields["status"] = "Unverified"
                elif job.status == "Unverified":
                    fields["status"] = "Open"
            if fields:
                job = update_job(conn, job.id, fields)
            updated.append(job)
    return updated


def _append_note(existing: str, note: str) -> str:
    if not note:
        return existing or ""
    if note in (existing or ""):
        return existing or ""
    return "; ".join(x for x in [existing, note] if x)
