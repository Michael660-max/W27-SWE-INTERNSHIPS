from __future__ import annotations

import re
from datetime import datetime, timezone

from .config import BIG_TECH_KEYWORDS, COMPETITIVE_COMPANY_KEYWORDS
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

FIT_TYPES = {
    "Backend Engineer Intern",
    "Full Stack Engineer Intern",
    "Platform Engineer Intern",
    "Infrastructure Engineer Intern",
    "AI Engineering Intern",
    "ML Engineering Intern",
    "Data Engineering Intern",
}


def _location_rank(job: JobRecord) -> int:
    """Lower is better for sort. Canada / Canada-remote first."""
    country = (job.country or "").lower()
    remote = (job.remote_or_hybrid or "").lower()
    loc = (job.location or "").lower()
    canada = "canada" in country or "canada" in loc
    if canada and remote == "remote":
        return 0
    if canada:
        return 1
    if remote == "remote":
        return 2
    if "united states" in country or "usa" in country or ", us" in loc:
        return 3
    return 4


def _company_rank(job: JobRecord) -> int:
    """Lower is better. Known high-signal companies first."""
    company_l = (job.company or "").lower()
    if any(k in company_l for k in BIG_TECH_KEYWORDS):
        return 0
    return 1


def is_competitive_company(company: str) -> bool:
    """Keyword-list check — use job_is_competitive() when a full JobRecord is available."""
    company_l = (company or "").lower().strip()
    # Some GitHub rows retain a Markdown company link. Match its label, not URL text.
    markdown_label = re.search(r"\[([^\]]+)\]\(", company_l)
    if markdown_label:
        company_l = markdown_label.group(1)
    company_l = company_l.strip("*_ ")
    return any(
        re.search(
            rf"(?<![a-z0-9]){re.escape(keyword.lower())}(?![a-z0-9])",
            company_l,
        )
        for keyword in COMPETITIVE_COMPANY_KEYWORDS
    )


def job_is_competitive(job: "JobRecord") -> bool:
    """True if the job is competitive.

    Agent judgment (``agent_competitive``) takes priority when the agent explicitly
    rated the company during discovery.  Falls back to the static keyword list so
    that Layer-1 rows (GitHub / Simplify) are still classified without agent input.
    """
    if job.agent_competitive is not None:
        return bool(job.agent_competitive)
    return is_competitive_company(job.company)


def _eligibility_rank(job: JobRecord) -> int:
    """Lower is better. Fewer hard eligibility gates first."""
    score = 0
    if job.requires_us_citizenship:
        score += 2
    if job.requires_export_control:
        score += 2
    if job.requires_us_work_auth:
        notes = (job.eligibility_notes or "").lower()
        if "no sponsorship" in notes or "cannot sponsor" in notes:
            score += 2
        else:
            score += 1
    return score


def compute_priority_score(job: JobRecord, now: datetime | None = None) -> int:
    """
    Numeric fit score used inside sort_jobs (higher = better).
    Factors: freshness/age, role fit, location, company quality, eligibility.
    """
    now = now or datetime.now(timezone.utc)
    score = 0

    country = (job.country or "").lower()
    remote = (job.remote_or_hybrid or "").lower()
    loc = (job.location or "").lower()

    # Location
    if "canada" in country or "canada" in loc:
        score += 3
    if remote == "remote" and ("canada" in country or "canada" in loc or "remote in canada" in loc):
        score += 3

    # Company quality
    company_l = (job.company or "").lower()
    if any(k in company_l for k in BIG_TECH_KEYWORDS):
        score += 2

    # Role fit
    role = job.normalized_role_type or ""
    title_l = (job.exact_role_title or "").lower()
    if role in CORE_TYPES or any(
        k in title_l for k in ("software engineer", "software developer", "swe")
    ):
        score += 2
    if role in FIT_TYPES or any(
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

    # Freshness / posting age
    if (job.freshness_label or "") == "Fresh":
        score += 2
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

    # Eligibility (penalties)
    if job.requires_us_citizenship:
        score -= 2
    if job.requires_export_control:
        score -= 2
    if job.requires_us_work_auth and "unclear" in (job.eligibility_notes or "").lower():
        score -= 2
    if job.requires_us_work_auth and not job.requires_us_citizenship:
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
    """
    Rank for Discord / LISTINGS / UI:
    1. Freshness label
    2. Posting datetime (newer first)
    3. Priority / fit score
    4. Location (Canada / Canada-remote first)
    5. Company quality
    6. Eligibility (fewer gates first)
    """

    def key(j: JobRecord):
        return (
            FRESHNESS_RANK.get(j.freshness_label or "", 9),
            -posting_sort_key(j.posting_date),
            -int(j.priority_score or 0),
            _location_rank(j),
            _company_rank(j),
            _eligibility_rank(j),
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
