from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from rapidfuzz import fuzz

from .db import (
    add_source,
    find_by_canonical_url,
    find_by_fingerprint,
    find_by_requisition,
    insert_job,
    merge_source_names,
    touch_seen_url,
    update_job,
    utc_now_iso,
)
from .freshness import label_freshness, previous_run_cutoff, toronto_now
from .models import CandidateJob, JobRecord, UpsertResult
from .score import compute_priority_score


def upsert_candidates(
    conn: sqlite3.Connection,
    candidates: list[CandidateJob],
    now: datetime | None = None,
) -> UpsertResult:
    result = UpsertResult()
    now = now or datetime.now(timezone.utc)
    now_iso = now.replace(microsecond=0).isoformat()
    window_start = previous_run_cutoff(toronto_now(now))
    existing_all = [
        dict(r)
        for r in conn.execute(
            "SELECT id, company, exact_role_title, location, term, normalized_role_type FROM jobs"
        ).fetchall()
    ]

    for cand in candidates:
        match = _find_match(conn, cand)
        if match is None:
            fuzzy = _fuzzy_warning(cand, existing_all)
            if fuzzy:
                result.fuzzy_warnings.append(fuzzy)

            posting_iso = cand.posting_date.replace(microsecond=0).isoformat() if cand.posting_date else None
            freshness = label_freshness(cand.posting_date, now, window_start)
            source_names = cand.source_name or ""
            agent_only = 1 if (cand.source_name or "").startswith("Cursor Agent") else 0

            fields = {
                "company": cand.company,
                "exact_role_title": cand.exact_role_title,
                "normalized_role_type": cand.normalized_role_type,
                "location": cand.location,
                "country": cand.country,
                "remote_or_hybrid": cand.remote_or_hybrid,
                "term": cand.term,
                "start_date": cand.start_date,
                "end_date": cand.end_date,
                "posting_date": posting_iso,
                "posting_date_precision": cand.posting_date_precision or "unknown",
                "first_found_at": now_iso,
                "last_seen_at": now_iso,
                "source_seen_at": now_iso,
                "official_url": cand.official_url,
                "canonical_url": cand.canonical_url,
                "source_url": cand.source_url,
                "requisition_id": cand.requisition_id,
                "ats_platform": cand.ats_platform,
                "source_names": source_names,
                "freshness_label": freshness,
                "eligibility_notes": cand.eligibility_notes,
                "requires_us_citizenship": int(cand.requires_us_citizenship),
                "requires_us_work_auth": int(cand.requires_us_work_auth),
                "requires_export_control": int(cand.requires_export_control),
                "status": "Open",
                "applied_status": "Not applied",
                "priority_score": 0,
                "notes": cand.notes,
                "raw_text_snapshot": cand.raw_text_snapshot[:20000],
                "application_deadline": cand.application_deadline,
                "agent_only": agent_only,
            }
            job = insert_job(conn, fields)
            score = compute_priority_score(job, now)
            job = update_job(conn, job.id, {"priority_score": score})
            add_source(conn, job.id, cand.source_name, cand.source_url or cand.official_url, now_iso)
            touch_seen_url(conn, cand.canonical_url, job.id, now_iso)
            touch_seen_url(conn, cand.official_url, job.id, now_iso)
            result.inserted.append(job)
            existing_all.append(
                {
                    "id": job.id,
                    "company": job.company,
                    "exact_role_title": job.exact_role_title,
                    "location": job.location,
                    "term": job.term,
                    "normalized_role_type": job.normalized_role_type,
                }
            )
        else:
            updates: dict = {
                "last_seen_at": now_iso,
                "source_seen_at": now_iso,
                "source_names": merge_source_names(match.source_names, cand.source_name),
            }
            # Prefer better official URL / posting date
            if cand.official_url and (
                not match.official_url or "simplify.jobs" in (match.official_url or "")
            ):
                if "simplify.jobs" not in cand.official_url or not match.official_url:
                    updates["official_url"] = cand.official_url
                    updates["canonical_url"] = cand.canonical_url or match.canonical_url
            if cand.posting_date and not match.posting_date:
                updates["posting_date"] = cand.posting_date.replace(microsecond=0).isoformat()
                updates["posting_date_precision"] = cand.posting_date_precision
            if cand.term and not match.term:
                updates["term"] = cand.term
            if cand.eligibility_notes and cand.eligibility_notes not in (match.eligibility_notes or ""):
                updates["eligibility_notes"] = "; ".join(
                    x for x in [match.eligibility_notes, cand.eligibility_notes] if x
                )
            if match.agent_only and cand.source_name and not cand.source_name.startswith("Cursor Agent"):
                updates["agent_only"] = 0

            job = update_job(conn, match.id, updates)
            score = compute_priority_score(job, now)
            job = update_job(conn, job.id, {"priority_score": score})
            add_source(conn, job.id, cand.source_name, cand.source_url or cand.official_url, now_iso)
            touch_seen_url(conn, cand.canonical_url, job.id, now_iso)
            result.updated.append(job)

    return result


def _find_match(conn: sqlite3.Connection, cand: CandidateJob) -> JobRecord | None:
    if cand.requisition_id:
        hit = find_by_requisition(conn, cand.requisition_id)
        if hit:
            return hit
    if cand.canonical_url:
        hit = find_by_canonical_url(conn, cand.canonical_url)
        if hit:
            return hit
    # Fingerprint uses exact title (not broad normalized type) to avoid over-merging
    return find_by_fingerprint(
        conn,
        cand.company,
        cand.exact_role_title,
        cand.location,
        cand.term,
    )


def _fuzzy_warning(cand: CandidateJob, existing: list[dict]) -> str | None:
    target = f"{cand.company} {cand.exact_role_title} {cand.location} {cand.term}".lower()
    best_score = 0
    best = None
    for row in existing:
        other = f"{row['company']} {row['exact_role_title']} {row['location']} {row['term']}".lower()
        score = fuzz.token_set_ratio(target, other)
        if score > best_score:
            best_score = score
            best = row
    if best and best_score >= 92:
        return (
            f"Likely duplicate (fuzzy {best_score}): "
            f"'{cand.company} — {cand.exact_role_title}' ~ "
            f"id={best['id']} '{best['company']} — {best['exact_role_title']}'"
        )
    return None
