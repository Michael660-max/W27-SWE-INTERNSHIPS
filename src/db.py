from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

from .config import DB_PATH
from .models import JobRecord


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL,
    exact_role_title TEXT NOT NULL,
    normalized_role_type TEXT DEFAULT '',
    location TEXT DEFAULT '',
    country TEXT DEFAULT '',
    remote_or_hybrid TEXT DEFAULT '',
    term TEXT DEFAULT '',
    start_date TEXT,
    end_date TEXT,
    posting_date TEXT,
    posting_date_precision TEXT DEFAULT 'unknown',
    first_found_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    source_seen_at TEXT NOT NULL,
    official_url TEXT DEFAULT '',
    canonical_url TEXT DEFAULT '',
    source_url TEXT DEFAULT '',
    requisition_id TEXT DEFAULT '',
    ats_platform TEXT DEFAULT '',
    source_names TEXT DEFAULT '',
    freshness_label TEXT DEFAULT '',
    eligibility_notes TEXT DEFAULT '',
    requires_us_citizenship INTEGER DEFAULT 0,
    requires_us_work_auth INTEGER DEFAULT 0,
    requires_export_control INTEGER DEFAULT 0,
    status TEXT DEFAULT 'Open',
    applied_status TEXT DEFAULT 'Not applied',
    priority_score INTEGER DEFAULT 0,
    notes TEXT DEFAULT '',
    raw_text_snapshot TEXT DEFAULT '',
    application_deadline TEXT,
    agent_only INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    source_name TEXT NOT NULL,
    source_url TEXT DEFAULT '',
    seen_at TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

CREATE TABLE IF NOT EXISTS seen_urls (
    url TEXT PRIMARY KEY,
    job_id INTEGER,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    sent_at TEXT NOT NULL,
    channel TEXT NOT NULL,
    payload TEXT DEFAULT '',
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

CREATE TABLE IF NOT EXISTS application_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    changed_at TEXT NOT NULL,
    notes TEXT DEFAULT '',
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    mode TEXT NOT NULL,
    inserted INTEGER DEFAULT 0,
    updated INTEGER DEFAULT 0,
    window_start TEXT,
    notes TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
CREATE INDEX IF NOT EXISTS idx_jobs_requisition ON jobs(requisition_id);
CREATE INDEX IF NOT EXISTS idx_jobs_canonical ON jobs(canonical_url);
CREATE INDEX IF NOT EXISTS idx_jobs_posting_date ON jobs(posting_date);
CREATE INDEX IF NOT EXISTS idx_sources_job ON sources(job_id);
CREATE INDEX IF NOT EXISTS idx_runs_finished ON runs(finished_at);
"""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_db(path: Path | None = None) -> Path:
    db_path = path or DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA)
        conn.commit()
    return db_path


@contextmanager
def connect(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    db_path = ensure_db(path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def row_to_job(row: sqlite3.Row) -> JobRecord:
    return JobRecord(**dict(row))


def get_job_by_id(conn: sqlite3.Connection, job_id: int) -> Optional[JobRecord]:
    cur = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cur.fetchone()
    return row_to_job(row) if row else None


def find_by_requisition(conn: sqlite3.Connection, requisition_id: str) -> Optional[JobRecord]:
    if not requisition_id:
        return None
    cur = conn.execute(
        "SELECT * FROM jobs WHERE requisition_id = ? AND requisition_id != '' LIMIT 1",
        (requisition_id,),
    )
    row = cur.fetchone()
    return row_to_job(row) if row else None


def find_by_canonical_url(conn: sqlite3.Connection, canonical_url: str) -> Optional[JobRecord]:
    if not canonical_url:
        return None
    cur = conn.execute(
        "SELECT * FROM jobs WHERE canonical_url = ? AND canonical_url != '' LIMIT 1",
        (canonical_url,),
    )
    row = cur.fetchone()
    return row_to_job(row) if row else None


def find_by_fingerprint(
    conn: sqlite3.Connection,
    company: str,
    exact_title: str,
    location: str,
    term: str,
) -> Optional[JobRecord]:
    cur = conn.execute(
        """
        SELECT * FROM jobs
        WHERE lower(company) = lower(?)
          AND lower(exact_role_title) = lower(?)
          AND lower(location) = lower(?)
          AND lower(term) = lower(?)
        LIMIT 1
        """,
        (company, exact_title, location, term),
    )
    row = cur.fetchone()
    return row_to_job(row) if row else None


def all_jobs(conn: sqlite3.Connection) -> list[JobRecord]:
    cur = conn.execute("SELECT * FROM jobs ORDER BY id")
    return [row_to_job(r) for r in cur.fetchall()]


def insert_job(conn: sqlite3.Connection, fields: dict[str, Any]) -> JobRecord:
    cols = list(fields.keys())
    placeholders = ", ".join("?" for _ in cols)
    col_names = ", ".join(cols)
    cur = conn.execute(
        f"INSERT INTO jobs ({col_names}) VALUES ({placeholders})",
        tuple(fields[c] for c in cols),
    )
    job_id = int(cur.lastrowid)
    job = get_job_by_id(conn, job_id)
    assert job is not None
    return job


def update_job(conn: sqlite3.Connection, job_id: int, fields: dict[str, Any]) -> JobRecord:
    if not fields:
        job = get_job_by_id(conn, job_id)
        assert job is not None
        return job
    sets = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(
        f"UPDATE jobs SET {sets} WHERE id = ?",
        (*fields.values(), job_id),
    )
    job = get_job_by_id(conn, job_id)
    assert job is not None
    return job


def add_source(
    conn: sqlite3.Connection,
    job_id: int,
    source_name: str,
    source_url: str,
    seen_at: str | None = None,
) -> None:
    seen = seen_at or utc_now_iso()
    conn.execute(
        "INSERT INTO sources (job_id, source_name, source_url, seen_at) VALUES (?, ?, ?, ?)",
        (job_id, source_name, source_url, seen),
    )


def touch_seen_url(
    conn: sqlite3.Connection,
    url: str,
    job_id: int,
    now: str | None = None,
) -> None:
    if not url:
        return
    now = now or utc_now_iso()
    existing = conn.execute("SELECT url FROM seen_urls WHERE url = ?", (url,)).fetchone()
    if existing:
        conn.execute(
            "UPDATE seen_urls SET job_id = ?, last_seen_at = ? WHERE url = ?",
            (job_id, now, url),
        )
    else:
        conn.execute(
            "INSERT INTO seen_urls (url, job_id, first_seen_at, last_seen_at) VALUES (?, ?, ?, ?)",
            (url, job_id, now, now),
        )


def record_notification(
    conn: sqlite3.Connection,
    job_id: int,
    channel: str,
    payload: dict[str, Any] | str,
) -> None:
    body = payload if isinstance(payload, str) else json.dumps(payload)
    conn.execute(
        "INSERT INTO notifications (job_id, sent_at, channel, payload) VALUES (?, ?, ?, ?)",
        (job_id, utc_now_iso(), channel, body),
    )


def merge_source_names(existing: str, new_name: str) -> str:
    names = [n.strip() for n in (existing or "").split(";") if n.strip()]
    if new_name and new_name not in names:
        names.append(new_name)
    return "; ".join(names)


def last_finished_run_at(conn: sqlite3.Connection) -> Optional[str]:
    row = conn.execute(
        """
        SELECT finished_at FROM runs
        WHERE finished_at IS NOT NULL AND finished_at != ''
        ORDER BY finished_at DESC
        LIMIT 1
        """
    ).fetchone()
    return row["finished_at"] if row else None


def start_run(
    conn: sqlite3.Connection,
    *,
    mode: str,
    window_start: str | None = None,
    notes: str = "",
) -> int:
    cur = conn.execute(
        """
        INSERT INTO runs (started_at, finished_at, mode, inserted, updated, window_start, notes)
        VALUES (?, NULL, ?, 0, 0, ?, ?)
        """,
        (utc_now_iso(), mode, window_start, notes),
    )
    return int(cur.lastrowid)


def finish_run(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    inserted: int = 0,
    updated: int = 0,
    notes: str | None = None,
) -> None:
    if notes is None:
        conn.execute(
            """
            UPDATE runs
            SET finished_at = ?, inserted = ?, updated = ?
            WHERE id = ?
            """,
            (utc_now_iso(), inserted, updated, run_id),
        )
    else:
        conn.execute(
            """
            UPDATE runs
            SET finished_at = ?, inserted = ?, updated = ?, notes = ?
            WHERE id = ?
            """,
            (utc_now_iso(), inserted, updated, notes, run_id),
        )
