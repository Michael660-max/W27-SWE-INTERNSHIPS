from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Allow `python src/main.py` from repo root
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent_ingest import collect_agent_findings  # noqa: E402
from src.config import AGENT_FINDINGS_DIR  # noqa: E402
from src.db import connect, ensure_db  # noqa: E402
from src.dedupe import upsert_candidates  # noqa: E402
from src.export_csv import export_csv  # noqa: E402
from src.models import CandidateJob  # noqa: E402
from src.notify import notify_new_jobs  # noqa: E402
from src.sources.company_ats import collect_company_ats  # noqa: E402
from src.sources.github_lists import collect_github_lists  # noqa: E402
from src.sources.simplify import collect_simplify  # noqa: E402
from src.verify import prefer_official_url, verify_and_update_jobs  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("w27")


def _prepare_candidate(cand: CandidateJob) -> CandidateJob:
    """Decode HTML entities in URLs and prefer official links — no network I/O."""
    import html

    for attr in ("official_url", "source_url", "canonical_url"):
        val = getattr(cand, attr, "") or ""
        if val:
            setattr(cand, attr, html.unescape(val).strip())
    return prefer_official_url(cand)


def collect_all(skip_ats: bool = False) -> list[CandidateJob]:
    candidates: list[CandidateJob] = []
    try:
        candidates.extend(collect_simplify())
    except Exception as exc:
        logger.exception("Simplify failed: %s", exc)
    try:
        candidates.extend(collect_github_lists())
    except Exception as exc:
        logger.exception("GitHub lists failed: %s", exc)
    if not skip_ats:
        try:
            candidates.extend(collect_company_ats())
        except Exception as exc:
            logger.exception("Company ATS failed: %s", exc)
    try:
        candidates.extend(collect_agent_findings())
    except Exception as exc:
        logger.exception("Agent findings failed: %s", exc)
    return candidates


def run_pipeline(
    dry_run: bool = False,
    skip_ats: bool = False,
    skip_verify: bool = False,
    ingest_only: Path | None = None,
) -> int:
    ensure_db()
    if ingest_only:
        candidates = collect_agent_findings(ingest_only)
    else:
        candidates = collect_all(skip_ats=skip_ats)

    logger.info("Collected %d raw candidates", len(candidates))

    # Light cleanup only (no HTTP) before upsert — full verify runs on inserts.
    candidates = [_prepare_candidate(c) for c in candidates]

    with connect() as conn:
        result = upsert_candidates(conn, candidates)
        logger.info(
            "Upsert: %d inserted, %d updated, %d fuzzy warnings",
            len(result.inserted),
            len(result.updated),
            len(result.fuzzy_warnings),
        )
        for warn in result.fuzzy_warnings[:20]:
            logger.warning(warn)

        if result.inserted and not skip_verify:
            # Cap verification volume for large first runs
            to_verify = result.inserted[:150]
            logger.info("Verifying %d newly inserted roles (capped)", len(to_verify))
            verify_and_update_jobs(conn, to_verify)
            unverified_rest = result.inserted[150:]
            if unverified_rest:
                from src.db import update_job

                for job in unverified_rest:
                    update_job(conn, job.id, {"status": "Unverified"})

        notify_path = notify_new_jobs(conn, result.inserted, dry_run=dry_run)
        if notify_path:
            logger.info("Wrote notification %s", notify_path)
        elif result.inserted:
            logger.info("New roles inserted but notification file skipped unexpectedly")
        else:
            logger.info("No new roles — skipping Discord")

    csv_path = export_csv()
    logger.info("Exported CSV %s", csv_path)
    return len(result.inserted)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Winter/Spring 2027 internship tracker")
    parser.add_argument("--dry-run", action="store_true", help="Skip Discord webhook send")
    parser.add_argument("--skip-ats", action="store_true", help="Skip company ATS boards")
    parser.add_argument("--skip-verify", action="store_true", help="Skip HTTP verification")
    parser.add_argument(
        "--ingest-findings",
        type=Path,
        nargs="?",
        const=AGENT_FINDINGS_DIR,
        help="Only ingest agent findings JSON from directory",
    )
    parser.add_argument("--export-csv-only", action="store_true")
    args = parser.parse_args(argv)

    if args.export_csv_only:
        ensure_db()
        path = export_csv()
        print(path)
        return 0

    inserted = run_pipeline(
        dry_run=args.dry_run,
        skip_ats=args.skip_ats,
        skip_verify=args.skip_verify,
        ingest_only=args.ingest_findings,
    )
    print(f"Inserted {inserted} new roles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
