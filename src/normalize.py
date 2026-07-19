from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import parse_qs, urlparse, urlunparse

from dateutil import parser as date_parser

from .config import EXCLUDE_ROLE_KEYWORDS, INCLUDE_ROLE_KEYWORDS, TARGET_TERMS
from .models import CandidateJob

RELATIVE_AGE_RE = re.compile(
    r"(?:🔥\s*)?(?P<num>\d+)\s*(?P<unit>d|h|mo|w|m|hr|hrs|day|days|week|weeks|month|months)\b",
    re.I,
)
CLOSED_RE = re.compile(r"\b(closed|expired|no longer available|position filled)\b", re.I)
CITIZENSHIP_RE = re.compile(
    r"(u\.?s\.?\s*citizen|united states citizen|must be.*citizen|citizenship required|🇺🇸|🛂)",
    re.I,
)
WORK_AUTH_RE = re.compile(
    r"(work authorization|authorized to work|must have.*authorization|no sponsorship|cannot sponsor)",
    re.I,
)
EXPORT_RE = re.compile(r"(export control|itar|ear\b|security clearance)", re.I)
SUMMER_ONLY_RE = re.compile(r"\bsummer\s*2027\b", re.I)
WINTER_SPRING_RE = re.compile(
    r"\b(winter|spring|jan(?:uary)?(?:\s*[-–/]\s*(?:apr(?:il)?|may))?|off[- ]?cycle)\b.*\b2027\b"
    r"|\b2027\b.*\b(winter|spring)\b",
    re.I,
)
FALL_ONLY_RE = re.compile(r"\bfall\s*2026\b", re.I)
REMOTE_RE = re.compile(r"\bremote\b", re.I)
HYBRID_RE = re.compile(r"\bhybrid\b", re.I)
CANADA_RE = re.compile(
    r"\b(canada|toronto|vancouver|montreal|ottawa|calgary|edmonton|waterloo|kitchener|"
    r"ontario|british columbia|quebec|alberta|manitoba|saskatchewan|nova scotia|"
    r"\bON\b|\bBC\b|\bQC\b|\bAB\b)\b",
    re.I,
)
US_RE = re.compile(
    r"\b(USA|U\.S\.|United States|\bCA\b|\bNY\b|\bTX\b|\bWA\b|\bMA\b|\bIL\b|\bSF\b|"
    r"San Francisco|New York|Seattle|Austin|Boston|Chicago|Remote in USA)\b",
    re.I,
)


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def clean_company(name: str) -> str:
    name = strip_html(name)
    name = re.sub(r"^[🔥🔒🎓🛂🇺🇸\s]+", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def clean_title(title: str) -> str:
    title = strip_html(title)
    title = re.sub(r"[🔒🎓🛂🇺🇸🔥]", "", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title


def canonicalize_url(url: str) -> str:
    if not url:
        return ""
    import html

    url = html.unescape(url.strip())
    try:
        parsed = urlparse(url)
    except Exception:
        return url
    # Drop tracking params
    qs = parse_qs(parsed.query)
    drop = {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_content",
        "utm_term",
        "gh_src",
        "source",
        "ref",
    }
    kept = {k: v for k, v in qs.items() if k.lower() not in drop}
    query = "&".join(f"{k}={v[0]}" for k, v in sorted(kept.items()) if v)
    path = parsed.path.rstrip("/") or ""
    return urlunparse((parsed.scheme, parsed.netloc.lower(), path, "", query, ""))


def extract_requisition_id(url: str, text: str = "") -> str:
    patterns = [
        r"[?&]gh_jid=(\d+)",
        r"/jobs/(\d{5,})",
        r"/job/(\d{5,})",
        r"REQ[-_]?(\d+)",
        r"JR(\d+)",
        r"requisition[_-]?id[=:]?\s*([A-Za-z0-9_-]+)",
        r"/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    ]
    blob = f"{url} {text}"
    for pat in patterns:
        m = re.search(pat, blob, re.I)
        if m:
            return m.group(1)
    return ""


def detect_ats(url: str) -> str:
    u = (url or "").lower()
    mapping = [
        ("greenhouse", "greenhouse"),
        ("lever.co", "lever"),
        ("ashbyhq", "ashby"),
        ("myworkdayjobs", "workday"),
        ("workday", "workday"),
        ("smartrecruiters", "smartrecruiters"),
        ("icims", "icims"),
        ("eightfold", "eightfold"),
        ("jobvite", "jobvite"),
        ("successfactors", "successfactors"),
        ("rippling.com", "rippling"),
        ("ats.rippling", "rippling"),
    ]
    for needle, name in mapping:
        if needle in u:
            return name
    return ""


def parse_relative_age(age_text: str, now: Optional[datetime] = None) -> tuple[Optional[datetime], str]:
    if not age_text:
        return None, "unknown"
    now = now or datetime.now(timezone.utc)
    m = RELATIVE_AGE_RE.search(age_text)
    if not m:
        # Try absolute date
        try:
            dt = date_parser.parse(age_text, fuzzy=True)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt, "date"
        except Exception:
            return None, "unknown"
    num = int(m.group("num"))
    unit = m.group("unit").lower()
    if unit in {"h", "hr", "hrs"}:
        delta = timedelta(hours=num)
    elif unit in {"d", "day", "days"}:
        delta = timedelta(days=num)
    elif unit in {"w", "week", "weeks"}:
        delta = timedelta(weeks=num)
    else:  # mo / m / months
        delta = timedelta(days=30 * num)
    return now - delta, "relative"


def extract_term(text: str) -> str:
    t = text.lower()
    terms: list[str] = []
    if re.search(r"winter\s*2027", t):
        terms.append("Winter 2027")
    if re.search(r"spring\s*2027", t):
        terms.append("Spring 2027")
    if re.search(r"jan(?:uary)?\s*[-–/]\s*apr(?:il)?\s*2027|january\s*[-–]\s*april\s*2027", t):
        terms.append("January-April 2027")
    if re.search(r"jan(?:uary)?\s*[-–/]\s*may\s*2027|january\s*[-–]\s*may\s*2027", t):
        terms.append("January-May 2027")
    if re.search(r"off[- ]?cycle\s*2027", t) and not terms:
        terms.append("Off-cycle 2027")
    if re.search(r"\bjan(?:uary)?\s*2027\b", t) and "Winter 2027" not in terms:
        terms.append("January 2027")
    return ", ".join(dict.fromkeys(terms))


def matches_target_term(text: str) -> bool:
    t = text.lower()
    if any(term in t for term in TARGET_TERMS):
        return True
    return bool(WINTER_SPRING_RE.search(t))


def is_summer_only(text: str) -> bool:
    t = text.lower()
    if not SUMMER_ONLY_RE.search(t):
        return False
    return not matches_target_term(t)


def is_fall_2026_only(text: str) -> bool:
    t = text.lower()
    if not FALL_ONLY_RE.search(t):
        return False
    return not matches_target_term(t)


def is_software_role(title: str, text: str = "") -> bool:
    blob = f"{title} {text}".lower()
    if any(k in blob for k in EXCLUDE_ROLE_KEYWORDS):
        # Allow if also strongly software + intern/co-op and not new grad FT
        if "new grad" in blob or "university grad" in blob:
            if "intern" not in blob and "co-op" not in blob and "coop" not in blob:
                return False
        if any(
            k in blob
            for k in (
                "helpdesk",
                "help desk",
                "business analyst",
                "data analyst",
                "it support",
                "desktop support",
                "customer support",
                "sales intern",
                "marketing intern",
                "hr intern",
            )
        ):
            return False
    return any(k in blob for k in INCLUDE_ROLE_KEYWORDS)


def normalize_role_type(title: str) -> str:
    t = title.lower()
    mapping = [
        ("site reliability", "SRE Intern"),
        ("sre", "SRE Intern"),
        ("devops", "DevOps Intern"),
        ("data engineer", "Data Engineering Intern"),
        ("machine learning", "ML Engineering Intern"),
        ("ml engineer", "ML Engineering Intern"),
        ("ai engineer", "AI Engineering Intern"),
        ("embedded", "Embedded Software Intern"),
        ("firmware", "Firmware Intern"),
        ("security", "Security Engineering Intern"),
        ("developer tools", "Developer Tools Intern"),
        ("platform", "Platform Engineer Intern"),
        ("infrastructure", "Infrastructure Engineer Intern"),
        ("cloud", "Cloud Engineer Intern"),
        ("full stack", "Full Stack Engineer Intern"),
        ("fullstack", "Full Stack Engineer Intern"),
        ("frontend", "Frontend Engineer Intern"),
        ("front end", "Frontend Engineer Intern"),
        ("backend", "Backend Engineer Intern"),
        ("mobile", "Mobile Engineer Intern"),
        ("ios", "Mobile Engineer Intern"),
        ("android", "Mobile Engineer Intern"),
        ("co-op", "Software Developer Co-op"),
        ("coop", "Software Developer Co-op"),
        ("software developer", "Software Developer Intern"),
        ("software engineer", "Software Engineer Intern"),
        ("software", "Software Engineer Intern"),
    ]
    for needle, label in mapping:
        if needle in t:
            return label
    return "Software Engineer Intern"


def detect_country(location: str, text: str = "") -> str:
    blob = f"{location} {text}"
    canada = bool(CANADA_RE.search(blob))
    us = bool(US_RE.search(blob))
    if canada and not us:
        return "Canada"
    if us and not canada:
        return "United States"
    if canada and us:
        return "Canada/US"
    if REMOTE_RE.search(blob) and "canada" in blob.lower():
        return "Canada"
    return ""


def detect_remote(location: str, text: str = "") -> str:
    blob = f"{location} {text}"
    if HYBRID_RE.search(blob):
        return "Hybrid"
    if REMOTE_RE.search(blob):
        return "Remote"
    return "Onsite"


def detect_eligibility(text: str) -> tuple[bool, bool, bool, str]:
    notes: list[str] = []
    cit = bool(CITIZENSHIP_RE.search(text))
    auth = bool(WORK_AUTH_RE.search(text))
    export = bool(EXPORT_RE.search(text))
    if cit:
        notes.append("U.S. citizenship required")
    if auth:
        notes.append("U.S. work authorization required")
    if export:
        notes.append("Export-control eligibility required")
    return cit, auth, export, "; ".join(notes)


def should_keep_candidate(candidate: CandidateJob) -> tuple[bool, str]:
    blob = " ".join(
        [
            candidate.company,
            candidate.exact_role_title,
            candidate.location,
            candidate.term,
            candidate.raw_text_snapshot,
            candidate.notes,
        ]
    )
    if CLOSED_RE.search(blob) and "open" not in blob.lower():
        return False, "closed_or_expired"
    if not is_software_role(candidate.exact_role_title, blob):
        return False, "not_software"
    if is_summer_only(blob):
        return False, "summer_only"
    if is_fall_2026_only(blob):
        return False, "fall_2026_only"
    # Prefer explicit term match; allow if term field already set to target
    if candidate.term and matches_target_term(candidate.term):
        return True, "ok"
    if matches_target_term(blob):
        return True, "ok"
    # Company ATS listings may lack season in title — keep if intern/co-op software
    title_l = candidate.exact_role_title.lower()
    if ("intern" in title_l or "co-op" in title_l or "coop" in title_l) and is_software_role(
        candidate.exact_role_title, blob
    ):
        # Without term, keep as unverified later; mark for term unknown
        return True, "ok_term_unknown"
    return False, "no_target_term"


def enrich_candidate(candidate: CandidateJob) -> CandidateJob:
    candidate.company = clean_company(candidate.company)
    candidate.exact_role_title = clean_title(candidate.exact_role_title)
    candidate.location = strip_html(candidate.location)
    candidate.official_url = (candidate.official_url or candidate.source_url or "").strip()
    candidate.canonical_url = canonicalize_url(candidate.official_url or candidate.source_url)
    if not candidate.requisition_id:
        candidate.requisition_id = extract_requisition_id(
            candidate.official_url or candidate.source_url,
            candidate.raw_text_snapshot,
        )
    if not candidate.ats_platform:
        candidate.ats_platform = detect_ats(candidate.official_url or candidate.source_url)
    if not candidate.term:
        candidate.term = extract_term(
            f"{candidate.exact_role_title} {candidate.raw_text_snapshot} {candidate.notes}"
        )
    if not candidate.normalized_role_type:
        candidate.normalized_role_type = normalize_role_type(candidate.exact_role_title)
    if not candidate.country:
        candidate.country = detect_country(
            candidate.location, f"{candidate.raw_text_snapshot} {candidate.notes}"
        )
    if not candidate.remote_or_hybrid:
        candidate.remote_or_hybrid = detect_remote(
            candidate.location, candidate.raw_text_snapshot
        )
    cit, auth, export, notes = detect_eligibility(
        f"{candidate.exact_role_title} {candidate.raw_text_snapshot} {candidate.eligibility_notes}"
    )
    candidate.requires_us_citizenship = candidate.requires_us_citizenship or cit
    candidate.requires_us_work_auth = candidate.requires_us_work_auth or auth
    candidate.requires_export_control = candidate.requires_export_control or export
    if notes and notes not in candidate.eligibility_notes:
        candidate.eligibility_notes = "; ".join(
            x for x in [candidate.eligibility_notes, notes] if x
        )
    return candidate
