from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class CandidateJob:
    """Normalized candidate before DB upsert."""

    company: str
    exact_role_title: str
    location: str = ""
    country: str = ""
    remote_or_hybrid: str = ""
    term: str = ""
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    official_url: str = ""
    canonical_url: str = ""
    source_url: str = ""
    source_name: str = ""
    ats_platform: str = ""
    requisition_id: str = ""
    posting_date: Optional[datetime] = None
    posting_date_precision: str = "unknown"
    eligibility_notes: str = ""
    requires_us_citizenship: bool = False
    requires_us_work_auth: bool = False
    requires_export_control: bool = False
    raw_text_snapshot: str = ""
    normalized_role_type: str = ""
    notes: str = ""
    application_deadline: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.posting_date is not None:
            d["posting_date"] = self.posting_date.isoformat()
        return d


@dataclass
class JobRecord:
    id: int
    company: str
    exact_role_title: str
    normalized_role_type: str
    location: str
    country: str
    remote_or_hybrid: str
    term: str
    start_date: Optional[str]
    end_date: Optional[str]
    posting_date: Optional[str]
    posting_date_precision: str
    first_found_at: str
    last_seen_at: str
    source_seen_at: str
    official_url: str
    canonical_url: str
    source_url: str
    requisition_id: str
    ats_platform: str
    source_names: str
    freshness_label: str
    eligibility_notes: str
    requires_us_citizenship: int
    requires_us_work_auth: int
    requires_export_control: int
    status: str
    applied_status: str
    priority_score: int
    notes: str
    raw_text_snapshot: str
    application_deadline: Optional[str] = None
    agent_only: int = 0
    verify_fail_count: int = 0
    duplicate_of_id: Optional[int] = None
    duplicate_confidence: str = ""
    alert_tier: str = ""


@dataclass
class UpsertResult:
    inserted: list[JobRecord] = field(default_factory=list)
    updated: list[JobRecord] = field(default_factory=list)
    fuzzy_warnings: list[str] = field(default_factory=list)
    quarantined: int = 0