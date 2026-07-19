from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from ..config import GITHUB_SOURCES_PATH
from ..coverage import CollectBundle, SourceReport
from ..http_util import fetch_text, get_client
from ..models import CandidateJob
from ..normalize import enrich_candidate, should_keep_candidate
from .table_parse import github_raw_url, parse_listing_markdown

logger = logging.getLogger(__name__)


def load_github_sources(path: Path | None = None) -> list[dict[str, Any]]:
    path = path or GITHUB_SOURCES_PATH
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return list(data.get("sources") or [])


def collect_github_lists(path: Path | None = None) -> CollectBundle:
    sources = load_github_sources(path)
    all_jobs: list[CandidateJob] = []
    rejected: list[tuple[CandidateJob, str]] = []
    reports: list[SourceReport] = []

    with get_client() as client:
        for src in sources:
            name = src.get("name") or src.get("repo")
            repo = src["repo"]
            branch = src.get("branch") or "main"
            file_path = src.get("path") or "README.md"
            if src.get("kind") == "simplify_table" or "README-Off-Season" in file_path:
                reports.append(
                    SourceReport(name=str(name), status="skipped", detail="handled by simplify")
                )
                logger.info("Skipping %s (handled by simplify collector)", name)
                continue
            url = github_raw_url(repo, branch, file_path)
            page_url = f"https://github.com/{repo}/blob/{branch}/{file_path}"
            logger.info("Fetching GitHub list %s (%s)", name, url)
            try:
                text = fetch_text(url, client=client)
            except Exception as exc:
                err = str(exc).lower()
                status = "timeout" if "timeout" in err or "timed out" in err else "error"
                reports.append(SourceReport(name=str(name), status=status, error=str(exc)))
                logger.warning("Failed %s: %s", name, exc)
                continue

            raw_jobs = parse_listing_markdown(text, source_name=name, source_page_url=page_url)
            kept_here = 0
            for job in raw_jobs:
                if src.get("exclude_new_grad"):
                    title_l = job.exact_role_title.lower()
                    if "new grad" in title_l and "intern" not in title_l:
                        rejected.append((job, "new_grad"))
                        continue
                job.source_name = name
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
                all_jobs.append(job)
                kept_here += 1

            status = "zero" if kept_here == 0 else "ok"
            reports.append(
                SourceReport(
                    name=str(name),
                    status=status,
                    fetched=len(raw_jobs),
                    kept=kept_here,
                )
            )
            logger.info("%s: kept %d (parsed %d)", name, kept_here, len(raw_jobs))

    return CollectBundle(jobs=all_jobs, reports=reports, rejected=rejected)
