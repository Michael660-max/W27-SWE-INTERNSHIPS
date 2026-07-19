from __future__ import annotations

import logging
import sqlite3

from .db import quarantine_candidate
from .models import CandidateJob
from .normalize import enrich_candidate, should_keep_candidate

logger = logging.getLogger(__name__)


def decide_keep(
    candidate: CandidateJob,
    *,
    conn: sqlite3.Connection | None = None,
    soft_term_unknown: bool = False,
) -> tuple[bool, str]:
    """
    Enrich + filter with INCLUDE/EXCLUDE logs.
    Unclear rejects go to quarantine when conn is provided.
    """
    candidate = enrich_candidate(candidate)
    ok, reason = should_keep_candidate(candidate)
    if not ok and soft_term_unknown and reason == "no_target_term":
        title = (candidate.exact_role_title or "").lower()
        if "intern" in title or "co-op" in title or "coop" in title:
            ok, reason = True, "ok_term_unknown_soft"

    label = "INCLUDE" if ok else "EXCLUDE"
    logger.info(
        "%s [%s] %s — %s | %s",
        label,
        reason,
        candidate.company,
        (candidate.exact_role_title or "")[:80],
        candidate.term or "(no term)",
    )

    if not ok and conn is not None:
        quarantine_candidate(
            conn,
            company=candidate.company,
            exact_role_title=candidate.exact_role_title,
            location=candidate.location,
            term=candidate.term,
            official_url=candidate.official_url or candidate.source_url,
            source_name=candidate.source_name,
            reason=reason,
            detail="filtered by should_keep_candidate",
            raw_snapshot=candidate.raw_text_snapshot,
        )
    elif ok and reason in {"ok_term_unknown", "ok_term_unknown_soft"} and conn is not None:
        # Keep in pipeline but also park a note for manual review
        quarantine_candidate(
            conn,
            company=candidate.company,
            exact_role_title=candidate.exact_role_title,
            location=candidate.location,
            term=candidate.term,
            official_url=candidate.official_url or candidate.source_url,
            source_name=candidate.source_name,
            reason="term_unclear",
            detail="kept with unknown term; needs manual verification",
            raw_snapshot=candidate.raw_text_snapshot,
        )

    return ok, reason
