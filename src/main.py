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
from src.db import (  # noqa: E402
    all_jobs,
    connect,
    ensure_db,
    finish_run,
    get_job_by_id,
    start_run,
)
from src.dedupe import upsert_candidates  # noqa: E402
from src.export_csv import export_csv  # noqa: E402
from src.export_listings import export_listings  # noqa: E402
from src.freshness import window_start_for_run  # noqa: E402
from src.models import CandidateJob  # noqa: E402
from src.notify import notify_new_jobs  # noqa: E402
from src.score import sort_jobs  # noqa: E402
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


def collect_layer1(skip_ats: bool = False) -> list[CandidateJob]:
    """GitHub lists + Simplify + company ATS (once per scout)."""
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
    return candidates


def collect_all(skip_ats: bool = False) -> list[CandidateJob]:
    candidates = collect_layer1(skip_ats=skip_ats)
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
    mode = "dry_run" if dry_run else "live"
    notes = "ingest-findings" if ingest_only else "layer1+findings"

    if ingest_only:
        candidates = collect_agent_findings(ingest_only)
    else:
        candidates = collect_all(skip_ats=skip_ats)

    logger.info("Collected %d raw candidates", len(candidates))
    candidates = [_prepare_candidate(c) for c in candidates]

    with connect() as conn:
        window_start = window_start_for_run(conn)
        window_iso = window_start.replace(microsecond=0).isoformat()
        run_id = start_run(conn, mode=mode, window_start=window_iso, notes=notes)
        logger.info(
            "Run %s mode=%s window_start=%s (from last finished run or schedule fallback)",
            run_id,
            mode,
            window_iso,
        )

        result = upsert_candidates(conn, candidates, window_start=window_start)
        logger.info(
            "Upsert: %d inserted, %d updated, %d fuzzy warnings",
            len(result.inserted),
            len(result.updated),
            len(result.fuzzy_warnings),
        )
        for warn in result.fuzzy_warnings[:20]:
            logger.warning(warn)

        if result.inserted and not skip_verify:
            to_verify = result.inserted[:150]
            logger.info("Verifying %d newly inserted roles (capped)", len(to_verify))
            verify_and_update_jobs(conn, to_verify)
            unverified_rest = result.inserted[150:]
            if unverified_rest:
                from src.db import update_job

                for job in unverified_rest:
                    update_job(conn, job.id, {"status": "Unverified"})

        # Reload inserts after verify so Discord sees final status + apply URL.
        inserted_fresh = []
        for job in result.inserted:
            latest = get_job_by_id(conn, job.id)
            if latest:
                inserted_fresh.append(latest)
        notify_path = notify_new_jobs(conn, inserted_fresh, dry_run=dry_run)
        if notify_path:
            logger.info("Wrote notification %s", notify_path)
        elif result.inserted:
            logger.info(
                "Inserted %d role(s) but none notifiable (need Open + apply URL) — skipping Discord",
                len(result.inserted),
            )
        else:
            logger.info("No new roles — skipping Discord")

        finish_run(
            conn,
            run_id,
            inserted=len(result.inserted),
            updated=len(result.updated),
        )

    csv_path = export_csv()
    listings_path = export_listings()
    logger.info("Exported CSV %s", csv_path)
    logger.info("Exported listings %s", listings_path)
    return len(result.inserted)


def run_notify_test(n: int, dry_run: bool = False) -> int:
    """Send Discord notification for top N jobs already in the DB (verification helper)."""
    ensure_db()
    with connect() as conn:
        jobs = sort_jobs(all_jobs(conn))[: max(0, n)]
        if not jobs:
            logger.warning("No jobs in database to notify")
            return 0
        logger.info("Notify-test: sending %d jobs (dry_run=%s)", len(jobs), dry_run)
        path = notify_new_jobs(
            conn,
            jobs,
            dry_run=dry_run,
            prefix="**W27 notify-test** (not necessarily new inserts)",
            style="table",
            only_valid=False,
        )
        if path:
            logger.info("Wrote notification %s", path)
    return len(jobs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Winter/Spring 2027 internship tracker")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip Discord only; still scrape, upsert, export, and record a runs row",
    )
    parser.add_argument("--skip-ats", action="store_true", help="Skip company ATS boards")
    parser.add_argument("--skip-verify", action="store_true", help="Skip HTTP verification")
    parser.add_argument(
        "--ingest-findings",
        type=Path,
        nargs="?",
        const=AGENT_FINDINGS_DIR,
        help="Only ingest agent findings JSON from directory (no Layer 1 scrape)",
    )
    parser.add_argument("--export-csv-only", action="store_true")
    parser.add_argument(
        "--export-listings-only",
        action="store_true",
        help="Rebuild LISTINGS.md from SQLite only",
    )
    parser.add_argument(
        "--notify-test",
        type=int,
        nargs="?",
        const=3,
        metavar="N",
        help="Send Discord alert for top N DB jobs (default 3); for webhook verification",
    )
    args = parser.parse_args(argv)

    if args.export_csv_only:
        ensure_db()
        path = export_csv()
        print(path)
        return 0

    if args.export_listings_only:
        ensure_db()
        path = export_listings()
        print(path)
        return 0

    if args.notify_test is not None:
        sent = run_notify_test(args.notify_test, dry_run=args.dry_run)
        print(f"Notify-test sent {sent} roles")
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
