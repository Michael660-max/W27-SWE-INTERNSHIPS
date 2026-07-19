from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import CandidateJob
from ..normalize import (
    clean_company,
    clean_title,
    parse_relative_age,
    strip_html,
)
from ..urls import apply_url_score, best_apply_url

LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
HTML_LINK_RE = re.compile(r'href=["\']([^"\']+)["\']', re.I)


def github_raw_url(repo: str, branch: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"


def extract_links(cell: str) -> list[tuple[str, str]]:
    """Return list of (text, url)."""
    links: list[tuple[str, str]] = []
    for text, url in LINK_RE.findall(cell or ""):
        links.append((text.strip(), url.strip()))
    for url in HTML_LINK_RE.findall(cell or ""):
        if not any(u == url for _, u in links):
            links.append(("", url.strip()))
    return links


def pick_apply_url(cell: str, base: str = "") -> str:
    import html

    cell = html.unescape(cell or "")
    links = extract_links(cell)
    for url in HTML_LINK_RE.findall(cell):
        url = html.unescape(url.strip())
        if not any(u == url for _, u in links):
            links.append(("", url))
    if not links:
        return ""

    resolved = []
    for _, url in links:
        url = html.unescape(url)
        if base and url.startswith("/"):
            url = urljoin(base, url)
        resolved.append(url)
    # Prefer real apply/ATS URLs; never return a bare homepage if better exists
    best = best_apply_url(*resolved)
    if best:
        return best
    # Fallback: lowest score even if weak (caller may clear later)
    resolved.sort(key=apply_url_score)
    return resolved[0] if resolved and apply_url_score(resolved[0]) < 9 else ""


def parse_html_tables(markdown: str, source_name: str, source_page_url: str = "") -> list[CandidateJob]:
    soup = BeautifulSoup(markdown, "lxml")
    jobs: list[CandidateJob] = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        headers = [strip_html(c.get_text(" ", strip=True)).lower() for c in rows[0].find_all(["th", "td"])]
        # Map columns
        def col_idx(*names: str) -> Optional[int]:
            for i, h in enumerate(headers):
                for n in names:
                    if n in h:
                        return i
            return None

        company_i = col_idx("company", "organization", "employer")
        role_i = col_idx("role", "position", "title", "job")
        loc_i = col_idx("location", "loc")
        term_i = col_idx("term", "season", "date", "when")
        age_i = col_idx("age", "posted", "added", "days")
        link_i = col_idx("application", "apply", "link", "url")

        # Heuristic if no headers
        if company_i is None and role_i is None:
            # Assume company, role, location, term/age pattern
            company_i, role_i, loc_i = 0, 1, 2
            if len(headers) >= 4:
                term_i = 3
            if len(headers) >= 5:
                age_i = len(headers) - 2
            link_i = len(headers) - 1

        last_company = ""
        for tr in rows[1:]:
            cells = tr.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            texts = [c.decode_contents() if hasattr(c, "decode_contents") else str(c) for c in cells]
            plain = [strip_html(BeautifulSoup(t, "lxml").get_text(" ", strip=True)) for t in texts]

            def cell(i: Optional[int]) -> str:
                if i is None or i >= len(texts):
                    return ""
                return texts[i]

            def plain_cell(i: Optional[int]) -> str:
                if i is None or i >= len(plain):
                    return ""
                return plain[i]

            company = clean_company(plain_cell(company_i))
            if company in {"↳", "->", "→"}:
                company = ""
            title = clean_title(plain_cell(role_i) if role_i is not None else plain_cell(1))
            if title.startswith("↳"):
                title = clean_title(title.lstrip("↳").strip())
            if not title or title.lower() in {"company", "role", "position"}:
                continue
            if company:
                last_company = company
            else:
                company = last_company
            if not company or company == "Unknown":
                continue

            location = plain_cell(loc_i)
            term = plain_cell(term_i) if term_i is not None else ""
            age_text = plain_cell(age_i) if age_i is not None else ""
            apply_cell = cell(link_i) if link_i is not None else " ".join(texts)
            # Also harvest anchors from role/company cells
            url = pick_apply_url(apply_cell, source_page_url)
            if not url:
                url = pick_apply_url(" ".join(texts), source_page_url)
            # Prefer career link over simplify company page
            for _, u in extract_links(" ".join(texts)):
                if any(
                    x in u.lower()
                    for x in (
                        "greenhouse",
                        "lever.co",
                        "ashby",
                        "workday",
                        "myworkdayjobs",
                        "jobs.",
                        "careers.",
                        "rippling",
                    )
                ):
                    url = u
                    break

            posting_date, precision = parse_relative_age(age_text)
            raw = strip_html(" | ".join(plain))
            jobs.append(
                CandidateJob(
                    company=company,
                    exact_role_title=title,
                    location=location,
                    term=term,
                    official_url=url,
                    source_url=url or source_page_url,
                    source_name=source_name,
                    posting_date=posting_date,
                    posting_date_precision=precision,
                    raw_text_snapshot=raw,
                )
            )
    return jobs


def parse_pipe_tables(markdown: str, source_name: str, source_page_url: str = "") -> list[CandidateJob]:
    """Fallback for GitHub-flavored markdown pipe tables."""
    jobs: list[CandidateJob] = []
    lines = markdown.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line.startswith("|") or "|" not in line[1:]:
            i += 1
            continue
        block = [line]
        i += 1
        while i < len(lines) and lines[i].strip().startswith("|"):
            block.append(lines[i].strip())
            i += 1
        if len(block) < 2:
            continue
        rows = []
        for bl in block:
            if re.match(r"^\|?\s*:?-{3,}", bl):
                continue
            cols = [c.strip() for c in bl.strip("|").split("|")]
            rows.append(cols)
        if len(rows) < 2:
            continue
        headers = [h.lower() for h in rows[0]]

        def idx(*names: str) -> Optional[int]:
            for hi, h in enumerate(headers):
                for n in names:
                    if n in h:
                        return hi
            return None

        company_i = idx("company", "organization") or 0
        role_i = idx("role", "position", "title") or (1 if len(headers) > 1 else 0)
        loc_i = idx("location") or (2 if len(headers) > 2 else None)
        term_i = idx("term", "season")
        age_i = idx("age", "posted")
        link_i = idx("application", "apply", "link")

        last_company = ""
        for cols in rows[1:]:
            company = clean_company(strip_html(cols[company_i] if company_i < len(cols) else ""))
            if company:
                last_company = company
            else:
                company = last_company or "Unknown"
            title = clean_title(strip_html(cols[role_i] if role_i < len(cols) else ""))
            if not title:
                continue
            location = strip_html(cols[loc_i]) if loc_i is not None and loc_i < len(cols) else ""
            term = strip_html(cols[term_i]) if term_i is not None and term_i < len(cols) else ""
            age_text = strip_html(cols[age_i]) if age_i is not None and age_i < len(cols) else ""
            apply_raw = cols[link_i] if link_i is not None and link_i < len(cols) else " ".join(cols)
            url = pick_apply_url(apply_raw, source_page_url)
            if not url:
                url = pick_apply_url(" ".join(cols), source_page_url)
            posting_date, precision = parse_relative_age(age_text)
            jobs.append(
                CandidateJob(
                    company=company,
                    exact_role_title=title,
                    location=location,
                    term=term,
                    official_url=url,
                    source_url=url or source_page_url,
                    source_name=source_name,
                    posting_date=posting_date,
                    posting_date_precision=precision,
                    raw_text_snapshot=strip_html(" | ".join(cols)),
                )
            )
    return jobs


def parse_listing_markdown(markdown: str, source_name: str, source_page_url: str = "") -> list[CandidateJob]:
    jobs = parse_html_tables(markdown, source_name, source_page_url)
    if len(jobs) < 3:
        jobs.extend(parse_pipe_tables(markdown, source_name, source_page_url))
    # Dedupe within parse by company+title+url
    seen = set()
    unique: list[CandidateJob] = []
    for j in jobs:
        key = (j.company.lower(), j.exact_role_title.lower(), j.official_url)
        if key in seen:
            continue
        seen.add(key)
        unique.append(j)
    return unique
