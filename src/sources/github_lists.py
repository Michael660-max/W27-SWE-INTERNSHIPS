from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from ..config import GITHUB_SOURCES_PATH
from ..http_util import fetch_text, get_client
from ..models import CandidateJob
from ..normalize import enrich_candidate, should_keep_candidate
from .table_parse import github_raw_url, parse_listing_markdown

logger = logging.getLogger(__name__)


def load_github_sources(path: Path | None = None) -> list[dict[str, Any]]:
    path = path or GITHUB_SOURCES_PATH
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return list(data.get("sources") or [])


def collect_github_lists(path: Path | None = None) -> list[CandidateJob]:
    sources = load_github_sources(path)
    all_jobs: list[CandidateJob] = []
    with get_client() as client:
        for src in sources:
            name = src.get("name") or src.get("repo")
            repo = src["repo"]
            branch = src.get("branch") or "main"
            file_path = src.get("path") or "README.md"
            # Skip Simplify Off-Season here — collected by simplify.py to avoid double fetch
            if src.get("kind") == "simplify_table" or "README-Off-Season" in file_path:
                logger.info("Skipping %s (handled by simplify collector)", name)
                continue
            url = github_raw_url(repo, branch, file_path)
            page_url = f"https://github.com/{repo}/blob/{branch}/{file_path}"
            logger.info("Fetching GitHub list %s (%s)", name, url)
            try:
                text = fetch_text(url, client=client)
            except Exception as exc:
                logger.warning("Failed %s: %s", name, exc)
                continue
            raw_jobs = parse_listing_markdown(text, source_name=name, source_page_url=page_url)
            for job in raw_jobs:
                if src.get("exclude_new_grad"):
                    title_l = job.exact_role_title.lower()
                    if "new grad" in title_l and "intern" not in title_l:
                        continue
                job.source_name = name
                job = enrich_candidate(job)
                ok, reason = should_keep_candidate(job)
                if not ok:
                    logger.debug("Skip [%s] %s — %s", name, job.exact_role_title, reason)
                    continue
                all_jobs.append(job)
            logger.info("%s: kept candidates so far %d (parsed %d)", name, len(all_jobs), len(raw_jobs))
    return all_jobs
