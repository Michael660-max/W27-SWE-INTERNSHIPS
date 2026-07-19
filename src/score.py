from __future__ import annotations

from datetime import datetime, timezone

from .config import BIG_TECH_KEYWORDS
from .freshness import FRESHNESS_RANK, posting_sort_key
from .models import JobRecord


CORE_TYPES = {
    "Backend Engineer Intern",
    "Full Stack Engineer Intern",
    "Platform Engineer Intern",
    "Infrastructure Engineer Intern",
    "Cloud Engineer Intern",
    "Data Engineering Intern",
    "ML Engineering Intern",
    "AI Engineering Intern",
    "Software Engineer Intern",
    "Software Developer Intern",
}


def compute_priority_score(job: JobRecord, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    score = 0

    country = (job.country or "").lower()
    remote = (job.remote_or_hybrid or "").lower()
    loc = (job.location or "").lower()

    if "canada" in country or "canada" in loc:
        score += 3
    if remote == "remote" and ("canada" in country or "canada" in loc or "remote in canada" in loc):
        score += 3

    company_l = (job.company or "").lower()
    if any(k in company_l for k in BIG_TECH_KEYWORDS):
        score += 2

    role = job.normalized_role_type or ""
    title_l = (job.exact_role_title or "").lower()
    if role in CORE_TYPES or any(
        k in title_l for k in ("software engineer", "software developer", "swe")
    ):
        score += 2
    if role in {
        "Backend Engineer Intern",
        "Full Stack Engineer Intern",
        "Platform Engineer Intern",
        "Infrastructure Engineer Intern",
        "AI Engineering Intern",
        "ML Engineering Intern",
        "Data Engineering Intern",
    } or any(
        k in title_l
        for k in (
            "backend",
            "full stack",
            "platform",
            "infra",
            "data engineer",
            "machine learning",
            "ai engineer",
        )
    ):
        score += 2

    # Posting-time boosts (dominant signal in scoring)
    pd = _parse_dt(job.posting_date)
    if pd is None:
        score -= 2
    else:
        age_h = (now - pd).total_seconds() / 3600.0
        if age_h <= 6:
            score += 5
        elif age_h <= 24:
            score += 4
        elif age_h <= 72:
            score += 2

    if job.requires_us_citizenship:
        score -= 2
    if job.requires_us_work_auth and "unclear" in (job.eligibility_notes or "").lower():
        score -= 2
    if job.requires_us_work_auth and not job.requires_us_citizenship:
        # Mild penalty for sponsorship-hostile roles when flagged
        if "no sponsorship" in (job.eligibility_notes or "").lower() or "cannot sponsor" in (
            job.eligibility_notes or ""
        ).lower():
            score -= 2

    non_core = any(
        k in title_l for k in ("analyst", "support", "coordinator", "operations intern")
    )
    if non_core:
        score -= 2

    if (job.status or "") == "Unverified" or (job.freshness_label or "") == "Late discovery":
        if pd is not None:
            age_d = (now - pd).total_seconds() / 86400.0
            if age_d > 7:
                score -= 3
        else:
            score -= 3
        if (job.status or "") == "Unverified":
            score -= 3

    return score


def sort_jobs(jobs: list[JobRecord]) -> list[JobRecord]:
    def key(j: JobRecord):
        return (
            FRESHNESS_RANK.get(j.freshness_label or "", 9),
            -posting_sort_key(j.posting_date),
            -int(j.priority_score or 0),
            -(1 if any(k in (j.company or "").lower() for k in BIG_TECH_KEYWORDS) else 0),
            j.application_deadline or "9999",
            j.company or "",
        )

    return sorted(jobs, key=key)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None
