from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "jobs.sqlite"
CSV_PATH = DATA_DIR / "jobs.csv"
GITHUB_SOURCES_PATH = DATA_DIR / "github_sources.yml"
COMPANIES_PATH = DATA_DIR / "companies.yml"
AGENT_FINDINGS_DIR = DATA_DIR / "agent_findings"
NOTIFICATIONS_DIR = DATA_DIR / "notifications"
RAW_SNAPSHOTS_DIR = DATA_DIR / "raw_snapshots"

TIMEZONE = "America/Toronto"
USER_AGENT = (
    "W27-SWE-Internships/1.0 (+https://github.com/Michael660-max/W27-SWE-INTERNSHIPS; "
    "internship research bot)"
)
HTTP_TIMEOUT = 30.0
HTTP_RETRIES = 2

# Freshness buffer for indexing delay
FRESHNESS_BUFFER_HOURS = 2

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()

TARGET_TERMS = (
    "winter 2027",
    "spring 2027",
    "january 2027",
    "jan 2027",
    "jan-apr 2027",
    "january-april 2027",
    "january-may 2027",
    "jan-may 2027",
    "off-cycle 2027",
    "winter/spring 2027",
)

SEARCH_TERMS = [
    "Winter 2027 software engineer intern",
    "Winter 2027 software developer co-op",
    "Spring 2027 software engineering intern",
    "Spring 2027 software developer co-op",
    "January 2027 software intern",
    "Jan 2027 software co-op",
    "2027 Winter software intern",
    "2027 Spring software intern",
    "off-cycle 2027 software intern",
    "backend intern Winter 2027",
    "frontend intern Winter 2027",
    "full stack intern Winter 2027",
    "platform intern Winter 2027",
    "infrastructure intern Winter 2027",
    "cloud intern Winter 2027",
    "DevOps intern Winter 2027",
    "SRE intern Winter 2027",
    "data engineer intern Winter 2027",
    "machine learning engineer intern Winter 2027",
    "AI engineer intern Winter 2027",
    "embedded software intern Winter 2027",
    "firmware intern Winter 2027",
    "security engineering intern Winter 2027",
    "developer tools intern Winter 2027",
]

BIG_TECH_KEYWORDS = {
    "google",
    "meta",
    "amazon",
    "apple",
    "microsoft",
    "netflix",
    "nvidia",
    "openai",
    "anthropic",
    "stripe",
    "shopify",
    "cloudflare",
    "datadog",
    "snowflake",
    "databricks",
    "palantir",
    "uber",
    "airbnb",
    "coinbase",
    "figma",
    "notion",
    "rippling",
    "ramp",
    "jane street",
    "citadel",
    "two sigma",
    "bloomberg",
    "roblox",
    "dropbox",
    "affirm",
    "tesla",
    "spacex",
    "adobe",
    "salesforce",
    "oracle",
    "ibm",
    "intel",
    "amd",
}

INCLUDE_ROLE_KEYWORDS = [
    "software engineer",
    "software developer",
    "software engineering",
    "backend",
    "front end",
    "frontend",
    "full stack",
    "fullstack",
    "mobile engineer",
    "ios engineer",
    "android engineer",
    "platform engineer",
    "infrastructure",
    "cloud engineer",
    "devops",
    "site reliability",
    "sre",
    "data engineer",
    "machine learning engineer",
    "ml engineer",
    "ai engineer",
    "embedded software",
    "firmware",
    "security engineer",
    "developer tools",
    "computer science co-op",
    "it software",
    "swe intern",
    "swe co-op",
    "software intern",
    "software co-op",
]

EXCLUDE_ROLE_KEYWORDS = [
    "new grad",
    "university grad",
    "full-time",
    "full time",
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
    "recruiter",
    "product manager intern",
    "program manager intern",
]

APPLIED_STATUSES = (
    "Not applied",
    "Applied",
    "Skipped",
    "Saved",
    "Interview",
    "Rejected",
    "Closed",
)

JOB_STATUSES = (
    "Open",
    "Closed",
    "Unverified",
    "Expired",
    "Duplicate",
)

FRESHNESS_LABELS = (
    "Fresh",
    "Late discovery",
    "Posting date unavailable",
)