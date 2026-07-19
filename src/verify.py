from __future__ import annotations

import sqlite3
from urllib.parse import urlparse

from .db import quarantine_candidate, update_job
from .http_util import get_client, head_or_get_ok
from .models import CandidateJob, JobRecord
from .normalize import matches_target_term
from .urls import apply_url_score


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

# Close only after this many failed checks across runs
VERIFY_FAILS_BEFORE_CLOSED = 2


def is_aggregator_url(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return False
    return host in AGGREGATOR_HOSTS or host.endswith(".simplify.jobs")


def prefer_official_url(candidate: CandidateJob) -> CandidateJob:
    """Prefer official ATS over aggregator (Simplify/LinkedIn/Indeed)."""
    official = candidate.official_url or ""
    source = candidate.source_url or ""
    # Lower score wins
    candidates = [u for u in (official, source) if u]
    if not candidates:
        return candidate
    best = min(candidates, key=apply_url_score)
    if best and best != official:
        candidate.official_url = best
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
    """
    Verify apply URLs. Temporary HTTP failures increment verify_fail_count;
    Closed only after VERIFY_FAILS_BEFORE_CLOSED failures across runs.
    """
    updated: list[JobRecord] = []
    with get_client() as client:
        for job in jobs:
            url = job.official_url or job.source_url
            fails = int(getattr(job, "verify_fail_count", 0) or 0)

            if not url or is_aggregator_url(url) or not _looks_like_job_url(url):
                fails += 1
                fields = {
                    "verify_fail_count": fails,
                    "status": "Closed" if fails >= VERIFY_FAILS_BEFORE_CLOSED else "Unverified",
                }
                quarantine_candidate(
                    conn,
                    company=job.company,
                    exact_role_title=job.exact_role_title,
                    location=job.location,
                    term=job.term,
                    official_url=url or "",
                    source_name=job.source_names,
                    reason="bad_http" if url else "no_apply_url",
                    detail=f"verify_fail_count={fails}",
                    raw_snapshot=job.raw_text_snapshot,
                )
                job = update_job(conn, job.id, fields)
                updated.append(job)
                continue

            ok, status, final_url = head_or_get_ok(url, client=client)
            fields: dict = {}
            if final_url and final_url != url and apply_url_score(final_url) <= apply_url_score(url):
                fields["official_url"] = final_url

            if not ok:
                fails += 1
                fields["verify_fail_count"] = fails
                fields["notes"] = _append_note(job.notes, f"Verification failed HTTP {status}")
                if fails >= VERIFY_FAILS_BEFORE_CLOSED:
                    fields["status"] = "Closed"
                else:
                    fields["status"] = "Unverified"
                quarantine_candidate(
                    conn,
                    company=job.company,
                    exact_role_title=job.exact_role_title,
                    location=job.location,
                    term=job.term,
                    official_url=url,
                    source_name=job.source_names,
                    reason="bad_http",
                    detail=f"HTTP {status}; verify_fail_count={fails}",
                    raw_snapshot=job.raw_text_snapshot,
                )
            else:
                fields["verify_fail_count"] = 0
                blob = f"{job.exact_role_title} {job.term} {job.raw_text_snapshot}"
                if job.term and not matches_target_term(blob) and "2027" not in (job.term or ""):
                    fields["status"] = "Unverified"
                    quarantine_candidate(
                        conn,
                        company=job.company,
                        exact_role_title=job.exact_role_title,
                        location=job.location,
                        term=job.term,
                        official_url=url,
                        source_name=job.source_names,
                        reason="term_unclear",
                        detail="term no longer matches target after verify",
                        raw_snapshot=job.raw_text_snapshot,
                    )
                elif job.status in {"Unverified", "Closed"}:
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
