from __future__ import annotations

import html
from urllib.parse import urlparse

from .models import JobRecord

ATS_MARKERS = (
    "boards.greenhouse.io",
    "job-boards.greenhouse.io",
    "boards-api.greenhouse.io",
    "lever.co",
    "jobs.lever.co",
    "ashbyhq.com",
    "jobs.ashbyhq.com",
    "myworkdayjobs.com",
    "ats.rippling.com",
    "smartrecruiters.com",
    "icims.com",
    "jobvite.com",
    "successfactors",
    "eightfold.ai",
    "greenhouse.io",
)

JOB_PATH_MARKERS = (
    "/job/",
    "/jobs/",
    "/careers/",
    "/opportunity/",
    "gh_jid=",
    "simplify.jobs/p/",
)


def clean_url(url: str) -> str:
    return html.unescape((url or "").strip())


def apply_url_score(url: str) -> int:
    """Lower is better. High scores = homepage / useless."""
    url = clean_url(url)
    if not url:
        return 100
    low = url.lower()
    try:
        parsed = urlparse(low)
    except Exception:
        return 90
    host = parsed.netloc
    path = parsed.path or ""

    if any(m in low for m in ATS_MARKERS):
        return 0
    if "simplify.jobs/p/" in low:
        return 1
    if any(m in low for m in JOB_PATH_MARKERS):
        return 2
    if "careers." in host or host.startswith("jobs."):
        return 3
    if "simplify.jobs/c/" in low:
        return 8
    if "github.com/" in low:
        return 9
    # Bare marketing homepage: scheme://host[/]
    if path in {"", "/"} and "job" not in low and "career" not in low:
        return 10
    if path.count("/") <= 1 and "job" not in path and "career" not in path:
        return 9
    return 5


def is_apply_url(url: str) -> bool:
    return apply_url_score(url) <= 3


def best_apply_url(*urls: str) -> str:
    scored = [(apply_url_score(u), clean_url(u)) for u in urls if u]
    if not scored:
        return ""
    scored.sort(key=lambda x: x[0])
    best_score, best = scored[0]
    if best_score >= 9:
        return ""  # refuse homepage as apply link
    return best


def job_apply_url(job: JobRecord) -> str:
    return best_apply_url(job.official_url or "", job.source_url or "", job.canonical_url or "")
