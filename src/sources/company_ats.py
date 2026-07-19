from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import yaml
from bs4 import BeautifulSoup

from ..config import COMPANIES_PATH, WATCHLIST_PATH
from ..coverage import CollectBundle, SourceReport
from ..http_util import fetch_json, fetch_text, get_client
from ..models import CandidateJob
from ..normalize import enrich_candidate, should_keep_candidate

logger = logging.getLogger(__name__)

INTERN_RE = re.compile(r"\b(intern|co-?op|co op)\b", re.I)
TERM_HINT_RE = re.compile(
    r"\b(winter|spring|january|jan|off-?cycle|2027)\b",
    re.I,
)


def load_companies(path: Path | None = None) -> list[dict[str, Any]]:
    path = path or COMPANIES_PATH
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return list(data.get("companies") or [])


def load_watchlist(path: Path | None = None) -> list[str]:
    path = path or WATCHLIST_PATH
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    names = []
    for item in data.get("companies") or []:
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict) and item.get("name"):
            names.append(str(item["name"]))
    return names


def collect_company_ats(path: Path | None = None) -> CollectBundle:
    companies = load_companies(path)
    watch = {n.lower() for n in load_watchlist()}
    # Ensure watchlist companies present in companies.yml are scraped first / flagged
    jobs: list[CandidateJob] = []
    rejected: list[tuple[CandidateJob, str]] = []
    reports: list[SourceReport] = []

    with get_client() as client:
        for company in companies:
            name = company["name"]
            ats = (company.get("ats") or "").lower()
            board_url = company["board_url"]
            is_watch = name.lower() in watch
            label = f"Company ATS:{name}" + (" [watchlist]" if is_watch else "")
            logger.info("Fetching ATS %s (%s)%s", name, ats, " WATCHLIST" if is_watch else "")
            try:
                if ats == "greenhouse":
                    found = _greenhouse(name, board_url, client)
                elif ats == "lever":
                    found = _lever(name, board_url, client)
                elif ats == "ashby":
                    found = _ashby(name, board_url, client)
                elif ats == "workday":
                    reports.append(
                        SourceReport(
                            name=label,
                            status="skipped",
                            detail="Workday needs Playwright",
                        )
                    )
                    continue
                else:
                    reports.append(
                        SourceReport(name=label, status="error", error=f"unknown ats {ats}")
                    )
                    continue
            except Exception as exc:
                err = str(exc).lower()
                status = "timeout" if "timeout" in err or "timed out" in err else "error"
                reports.append(SourceReport(name=label, status=status, error=str(exc)))
                logger.warning("ATS fetch failed for %s: %s", name, exc)
                continue

            kept_here = 0
            for job in found:
                job = enrich_candidate(job)
                ok, reason = should_keep_candidate(job)
                if not ok and reason == "no_target_term":
                    if INTERN_RE.search(job.exact_role_title):
                        ok, reason = True, "ok_term_unknown_soft"
                if not ok:
                    logger.debug(
                        "EXCLUDE [%s] %s — %s",
                        reason,
                        job.company,
                        (job.exact_role_title or "")[:80],
                    )
                    rejected.append((job, reason))
                    continue
                if is_watch:
                    job.notes = (job.notes + "; watchlist").strip("; ")
                logger.debug(
                    "INCLUDE [%s] %s — %s",
                    reason,
                    job.company,
                    (job.exact_role_title or "")[:80],
                )
                jobs.append(job)
                kept_here += 1

            status = "zero" if kept_here == 0 else "ok"
            # Watchlist zero is especially important
            if is_watch and status == "zero":
                status = "zero"
            reports.append(
                SourceReport(
                    name=label,
                    status=status,
                    fetched=len(found),
                    kept=kept_here,
                    detail="watchlist" if is_watch else "",
                )
            )

    logger.info("Company ATS kept %d", len(jobs))
    return CollectBundle(jobs=jobs, reports=reports, rejected=rejected)


def _greenhouse(company: str, board_url: str, client) -> list[CandidateJob]:
    jobs: list[CandidateJob] = []
    if "boards-api.greenhouse.io" in board_url:
        api = board_url
    else:
        token = _greenhouse_token(board_url)
        if not token:
            return jobs
        api = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"

    try:
        data = fetch_json(api, client=client)
    except Exception:
        html = fetch_text(board_url, client=client)
        soup = BeautifulSoup(html, "lxml")
        for a in soup.select("a[href*='jobs'], a[href*='job']"):
            title = a.get_text(" ", strip=True)
            if not INTERN_RE.search(title):
                continue
            href = a.get("href") or ""
            jobs.append(
                CandidateJob(
                    company=company,
                    exact_role_title=title,
                    official_url=href,
                    source_url=href,
                    source_name=f"Company ATS:{company}",
                    ats_platform="greenhouse",
                    raw_text_snapshot=title,
                )
            )
        return jobs

    for item in data.get("jobs") or []:
        title = item.get("title") or ""
        if not INTERN_RE.search(title):
            continue
        loc = ""
        if item.get("location"):
            loc = item["location"].get("name") or ""
        url = item.get("absolute_url") or ""
        jobs.append(
            CandidateJob(
                company=company,
                exact_role_title=title,
                location=loc,
                official_url=url,
                source_url=url,
                source_name=f"Company ATS:{company}",
                ats_platform="greenhouse",
                requisition_id=str(item.get("id") or ""),
                raw_text_snapshot=f"{title} | {loc}",
                posting_date_precision="unknown",
            )
        )
    return jobs


def _greenhouse_token(board_url: str) -> str:
    qs = parse_qs(urlparse(board_url).query)
    if "for" in qs:
        return qs["for"][0]
    parts = [p for p in urlparse(board_url).path.strip("/").split("/") if p]
    if "boards" in parts:
        try:
            i = parts.index("boards")
            return parts[i + 1]
        except (ValueError, IndexError):
            pass
    if parts:
        return parts[0]
    return ""


def _lever(company: str, board_url: str, client) -> list[CandidateJob]:
    data = fetch_json(board_url, client=client)
    jobs: list[CandidateJob] = []
    if not isinstance(data, list):
        return jobs
    for item in data:
        title = item.get("text") or ""
        if not INTERN_RE.search(title):
            continue
        cats = item.get("categories") or {}
        loc = cats.get("location") or ""
        url = item.get("hostedUrl") or item.get("applyUrl") or ""
        jobs.append(
            CandidateJob(
                company=company,
                exact_role_title=title,
                location=loc,
                official_url=url,
                source_url=url,
                source_name=f"Company ATS:{company}",
                ats_platform="lever",
                requisition_id=str(item.get("id") or ""),
                raw_text_snapshot=f"{title} | {loc} | {item.get('descriptionPlain', '')[:500]}",
                term=_term_from_text(f"{title} {item.get('descriptionPlain', '')}"),
            )
        )
    return jobs


def _ashby(company: str, board_url: str, client) -> list[CandidateJob]:
    data = fetch_json(board_url, client=client)
    jobs: list[CandidateJob] = []
    for item in data.get("jobs") or []:
        title = item.get("title") or ""
        if not INTERN_RE.search(title):
            continue
        loc = item.get("location") or ""
        if isinstance(loc, dict):
            loc = loc.get("name") or ""
        url = item.get("jobUrl") or item.get("applyUrl") or ""
        jobs.append(
            CandidateJob(
                company=company,
                exact_role_title=title,
                location=str(loc),
                official_url=url,
                source_url=url,
                source_name=f"Company ATS:{company}",
                ats_platform="ashby",
                requisition_id=str(item.get("id") or ""),
                raw_text_snapshot=f"{title} | {loc}",
                term=_term_from_text(title),
            )
        )
    return jobs


def _term_from_text(text: str) -> str:
    if not TERM_HINT_RE.search(text or ""):
        return ""
    from ..normalize import extract_term

    return extract_term(text)
