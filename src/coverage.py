from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .config import DATA_DIR
from .db import utc_now_iso

logger = logging.getLogger(__name__)

COVERAGE_DIR = DATA_DIR / "coverage"


@dataclass
class SourceReport:
    name: str
    status: str  # ok | error | timeout | zero | skipped
    fetched: int = 0
    kept: int = 0
    error: str = ""
    detail: str = ""


@dataclass
class CollectBundle:
    """Collector return: kept jobs + coverage + rejected (for quarantine)."""

    jobs: list = field(default_factory=list)
    reports: list[SourceReport] = field(default_factory=list)
    rejected: list = field(default_factory=list)  # list[tuple[CandidateJob, reason]]


@dataclass
class CoverageSummary:
    reports: list[SourceReport] = field(default_factory=list)
    rejected: list = field(default_factory=list)

    def extend_bundle(self, bundle: CollectBundle) -> list:
        for r in bundle.reports:
            self.add(r)
        self.rejected.extend(bundle.rejected)
        return list(bundle.jobs)

    def add(self, report: SourceReport) -> None:
        self.reports.append(report)
        level = logging.WARNING if report.status in {"error", "timeout", "zero"} else logging.INFO
        logger.log(
            level,
            "SOURCE %s status=%s fetched=%d kept=%d%s",
            report.name,
            report.status,
            report.fetched,
            report.kept,
            f" err={report.error}" if report.error else "",
        )

    def problems(self) -> list[SourceReport]:
        return [r for r in self.reports if r.status in {"error", "timeout", "zero"}]

    def to_dict(self) -> dict:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sources": [asdict(r) for r in self.reports],
            "problem_count": len(self.problems()),
        }


def persist_coverage(
    conn: sqlite3.Connection,
    run_id: int,
    summary: CoverageSummary,
) -> Path | None:
    """Write coverage rows + JSON artifact for the run."""
    now = utc_now_iso()
    for r in summary.reports:
        conn.execute(
            """
            INSERT INTO source_coverage
                (run_id, source_name, status, fetched, kept, error, detail, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, r.name, r.status, r.fetched, r.kept, r.error, r.detail, now),
        )
    COVERAGE_DIR.mkdir(parents=True, exist_ok=True)
    path = COVERAGE_DIR / f"run_{run_id}_{now.replace(':', '').replace('+', 'Z')}.json"
    # simplify filename
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = COVERAGE_DIR / f"{ts}_run{run_id}.json"
    path.write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")
    probs = summary.problems()
    if probs:
        logger.warning(
            "Source coverage: %d problem(s): %s",
            len(probs),
            ", ".join(f"{p.name}={p.status}" for p in probs),
        )
    else:
        logger.info("Source coverage: all %d sources healthy", len(summary.reports))
    logger.info("Wrote coverage log %s", path)
    return path


def run_collector(
    name: str,
    fn,
    summary: CoverageSummary,
) -> list:
    """Execute a collector and record coverage."""
    try:
        result = fn()
        if isinstance(result, CollectBundle):
            jobs = summary.extend_bundle(result)
            if not result.reports:
                status = "zero" if not jobs else "ok"
                summary.add(
                    SourceReport(name=name, status=status, fetched=len(jobs), kept=len(jobs))
                )
            return jobs
        jobs = list(result or [])
        status = "zero" if not jobs else "ok"
        summary.add(SourceReport(name=name, status=status, fetched=len(jobs), kept=len(jobs)))
        return jobs
    except TimeoutError as exc:
        summary.add(SourceReport(name=name, status="timeout", error=str(exc)))
        return []
    except Exception as exc:
        err = str(exc).lower()
        status = "timeout" if "timeout" in err or "timed out" in err else "error"
        summary.add(SourceReport(name=name, status=status, error=str(exc)))
        logger.exception("%s failed: %s", name, exc)
        return []
