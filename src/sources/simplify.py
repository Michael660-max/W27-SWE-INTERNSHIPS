from __future__ import annotations

import logging

from ..coverage import CollectBundle, SourceReport
from ..http_util import fetch_text, get_client
from ..models import CandidateJob
from ..normalize import enrich_candidate, should_keep_candidate
from .table_parse import github_raw_url, parse_listing_markdown

logger = logging.getLogger(__name__)

DEFAULT_REPO = "SimplifyJobs/Summer2026-Internships"
DEFAULT_BRANCH = "dev"
DEFAULT_PATH = "README-Off-Season.md"


def collect_simplify(
    repo: str = DEFAULT_REPO,
    branch: str = DEFAULT_BRANCH,
    path: str = DEFAULT_PATH,
) -> CollectBundle:
    url = github_raw_url(repo, branch, path)
    source_name = "Simplify Off-Season"
    logger.info("Fetching %s", url)
    with get_client() as client:
        text = fetch_text(url, client=client)
    page_url = f"https://github.com/{repo}/blob/{branch}/{path}"
    raw_jobs = parse_listing_markdown(text, source_name=source_name, source_page_url=page_url)

    kept: list[CandidateJob] = []
    rejected: list[tuple[CandidateJob, str]] = []
    for job in raw_jobs:
        job.source_name = source_name
        job = enrich_candidate(job)
        ok, reason = should_keep_candidate(job)
        if not ok:
            logger.debug(
                "EXCLUDE [%s] %s — %s",
                reason,
                job.company,
                (job.exact_role_title or "")[:80],
            )
            rejected.append((job, reason))
            continue
        logger.debug(
            "INCLUDE [%s] %s — %s",
            reason,
            job.company,
            (job.exact_role_title or "")[:80],
        )
        kept.append(job)

    status = "zero" if not kept else "ok"
    report = SourceReport(
        name=source_name,
        status=status,
        fetched=len(raw_jobs),
        kept=len(kept),
    )
    logger.info("Simplify kept %d / %d rows", len(kept), len(raw_jobs))
    return CollectBundle(jobs=kept, reports=[report], rejected=rejected)
