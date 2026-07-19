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
    quarantine_candidate,
    touch_seen_url,
    update_job,
)
from .freshness import label_freshness, window_start_for_run
from .models import CandidateJob, JobRecord, UpsertResult
from .score import compute_priority_score
from .urls import apply_url_score
from .watchlist import is_watchlist_company


def upsert_candidates(
    conn: sqlite3.Connection,
    candidates: list[CandidateJob],
    now: datetime | None = None,
    window_start: datetime | None = None,
) -> UpsertResult:
    result = UpsertResult()
    now = now or datetime.now(timezone.utc)
    now_iso = now.replace(microsecond=0).isoformat()
    window_start = window_start or window_start_for_run(conn, now)
    existing_all = [
        dict(r)
        for r in conn.execute(
            "SELECT id, company, exact_role_title, location, term, normalized_role_type FROM jobs"
        ).fetchall()
    ]

    for cand in candidates:
        match = _find_match(conn, cand)
        if match is None:
            conf, fuzzy_id, fuzzy_msg = _fuzzy_confidence(cand, existing_all)
            if fuzzy_msg:
                result.fuzzy_warnings.append(fuzzy_msg)
            if conf == "likely_duplicate" and fuzzy_id:
                # Do not auto-drop — insert but flag + quarantine for review
                quarantine_candidate(
                    conn,
                    company=cand.company,
                    exact_role_title=cand.exact_role_title,
                    location=cand.location,
                    term=cand.term,
                    official_url=cand.official_url or cand.source_url,
                    source_name=cand.source_name,
                    reason="likely_duplicate",
                    detail=fuzzy_msg or "",
                    raw_snapshot=cand.raw_text_snapshot,
                )
                result.quarantined += 1

            posting_iso = cand.posting_date.replace(microsecond=0).isoformat() if cand.posting_date else None
            freshness = label_freshness(cand.posting_date, now, window_start, first_found_at=now)
            source_names = cand.source_name or ""
            agent_only = 1 if (cand.source_name or "").startswith("Cursor Agent") else 0
            tier = _alert_tier(cand, freshness)

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
                "verify_fail_count": 0,
                "duplicate_of_id": fuzzy_id if conf in {"likely_duplicate", "possible_duplicate"} else None,
                "duplicate_confidence": conf,
                "alert_tier": tier,
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
                "duplicate_confidence": "exact_duplicate",
            }
            # Official ATS URL always wins over aggregator / worse scores
            preferred = _prefer_url(match.official_url, cand.official_url, cand.source_url)
            if preferred and preferred != (match.official_url or ""):
                updates["official_url"] = preferred
                if cand.canonical_url:
                    updates["canonical_url"] = cand.canonical_url
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

            # Refresh alert tier from latest freshness if we have posting date
            pd = None
            if cand.posting_date:
                pd = cand.posting_date
            freshness = label_freshness(pd, now, window_start, first_found_at=now)
            if cand.posting_date or not match.freshness_label:
                updates["freshness_label"] = match.freshness_label or freshness
            updates["alert_tier"] = _alert_tier(cand, updates.get("freshness_label") or match.freshness_label)

            job = update_job(conn, match.id, updates)
            score = compute_priority_score(job, now)
            job = update_job(conn, job.id, {"priority_score": score})
            add_source(conn, job.id, cand.source_name, cand.source_url or cand.official_url, now_iso)
            touch_seen_url(conn, cand.canonical_url, job.id, now_iso)
            result.updated.append(job)

    return result


def _prefer_url(*urls: str) -> str:
    scored = [(apply_url_score(u), u) for u in urls if u]
    if not scored:
        return ""
    scored.sort(key=lambda x: x[0])
    return scored[0][1]


def _alert_tier(cand: CandidateJob, freshness: str) -> str:
    watch = is_watchlist_company(cand.company) or "watchlist" in (cand.notes or "")
    title = (cand.exact_role_title or "").lower()
    unclear = not (cand.term or "").strip() or "unclear" in (cand.eligibility_notes or "").lower()
    if unclear:
        return "needs_manual_verification"
    if freshness == "Late discovery":
        return "late_discovery"
    if watch and freshness == "Fresh":
        return "apply_now"
    if freshness == "Fresh" or watch:
        return "good_lead"
    if any(k in title for k in ("software engineer", "software developer", "swe")):
        return "good_lead"
    return "good_lead"


def _find_match(conn: sqlite3.Connection, cand: CandidateJob) -> JobRecord | None:
    if cand.requisition_id:
        hit = find_by_requisition(conn, cand.requisition_id)
        if hit:
            return hit
    if cand.canonical_url:
        hit = find_by_canonical_url(conn, cand.canonical_url)
        if hit:
            return hit
    return find_by_fingerprint(
        conn,
        cand.company,
        cand.exact_role_title,
        cand.location,
        cand.term,
    )


def _fuzzy_confidence(
    cand: CandidateJob, existing: list[dict]
) -> tuple[str, int | None, str | None]:
    """
    Returns (confidence, other_id, message).
    exact is handled by _find_match; here we only score fuzzy neighbors.
    Never auto-drops — caller inserts with flags.
    """
    target = f"{cand.company} {cand.exact_role_title} {cand.location} {cand.term}".lower()
    best_score = 0
    best = None
    for row in existing:
        other = f"{row['company']} {row['exact_role_title']} {row['location']} {row['term']}".lower()
        score = fuzz.token_set_ratio(target, other)
        if score > best_score:
            best_score = score
            best = row
    if not best:
        return "", None, None
    if best_score >= 96:
        conf = "likely_duplicate"
    elif best_score >= 90:
        conf = "possible_duplicate"
    else:
        return "", None, None
    msg = (
        f"{conf.replace('_', ' ').title()} (fuzzy {best_score}): "
        f"'{cand.company} — {cand.exact_role_title}' ~ "
        f"id={best['id']} '{best['company']} — {best['exact_role_title']}'"
    )
    return conf, int(best["id"]), msg
