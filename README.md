# Winter / Spring 2027 SWE Internship Tracker

Deterministic scraper + SQLite database that aggregates Winter 2027 / Spring 2027 software internships and co-ops (Canada + US). Cursor Automations run twice on weekdays, scrape GitHub lists and company boards, optionally discover more roles via browsing, update the DB, commit results, and Discord-notify only **new** roles.

**Source of truth:** `data/jobs.sqlite`  
**Human view:** **[LISTINGS.md](LISTINGS.md)** (Simplify-style table with Source + Apply) · optional UI (`bash scripts/ui.sh`) · `data/jobs.csv`  
**Scheduler:** Cursor Automations (see [docs/AGENT_RUNBOOK.md](docs/AGENT_RUNBOOK.md))

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Full collect → verify → dedupe → LISTINGS.md + CSV (+ Discord if webhook set)
python src/main.py --dry-run

# Rebuild the markdown board only
python src/main.py --export-listings-only

# Optional live UI
bash scripts/ui.sh   # http://127.0.0.1:8787
```

### CLI

| Command | Purpose |
|---------|---------|
| `python src/main.py` | Scrape lists + ATS + ingest findings; refresh LISTINGS.md / CSV |
| `python src/main.py --dry-run` | Same, but do not POST to Discord |
| `python src/main.py --skip-ats` | Skip company career boards |
| `python src/main.py --ingest-findings` | Only ingest agent JSON findings |
| `python src/main.py --export-csv-only` | Rebuild CSV from SQLite |
| `python src/main.py --export-listings-only` | Rebuild [LISTINGS.md](LISTINGS.md) from SQLite |
| `python src/main.py --notify-test [N]` | Discord smoke test (table style) |
| `bash scripts/ui.sh` | Start live jobs UI on port 8787 |

## Listings board

Every scout regenerates [LISTINGS.md](LISTINGS.md), **filtered to Winter 2027** (plus January 2027 winter-term equivalents):

| Column | Meaning |
|--------|---------|
| Company / Role / Location / Term / Posted | Role identity |
| **Source** | Where we found it (Simplify, SpeedyApply, ATS, agent, …) |
| **Apply** | Official/ATS apply link when we have one; `—` if only a homepage was available |

## Architecture

1. **Layer 1 — Deterministic scrapers** (Simplify off-season, multiple GitHub internship repos, manual ATS list in `data/companies.yml`)
2. **Layer 2 — Cursor agent discovery** writes `data/agent_findings/*.json`, ingested into the same pipeline
3. **Layer 3 — Judgment** (optional): use ChatGPT/Cursor chat on the CSV/Discord output for ranking — not for persistence

## Posting time

Notifications and CSV sort by:

1. Freshness (`Fresh` → `Late discovery` → `Posting date unavailable`)
2. **Posting datetime** (newest first)
3. Priority score
4. Company tier

Relative ages from list tables (`3d`, `22d`) become approximate posting dates.

## GitHub sources

Configured in [`data/github_sources.yml`](data/github_sources.yml). Add repos without code changes.

## Schedule (America/Toronto)

| Run | Window |
|-----|--------|
| Weekdays 12:30 | Since previous 18:00 (Monday → Friday 18:00) |
| Weekdays 18:00 | Since same-day 12:30 |

Automations cron is UTC — see runbook for EDT/EST expressions.

## Discord

Set `DISCORD_WEBHOOK_URL` in the environment used by local runs / Cloud Agents. New-role alerts are a **short summary** linking to [LISTINGS.md](LISTINGS.md). Use `--notify-test` for a compact Discord table. Audit files go to `data/notifications/`.

## Cursor Automations (scheduled scouts)

Create two Automations (see [docs/AGENT_RUNBOOK.md](docs/AGENT_RUNBOOK.md)):

| Name | Toronto time | Cron (EDT) |
|------|--------------|------------|
| W27 Midday Scout | Weekdays 12:30 | `30 16 * * 1-5` |
| W27 Evening Scout | Weekdays 18:00 | `0 22 * * 1-5` |

Each run should: pull `main` → `bash scripts/run_scout.sh` → browse/search for new roles → write `data/agent_findings/<timestamp>.json` → `python src/main.py --ingest-findings` → commit/push `data/`.

Set `DISCORD_WEBHOOK_URL` in the Cloud Agent environment. After DST ends, shift cron +1 hour (EST).

## Application tracking

Prefer the UI applied-status dropdown. Values: `Not applied`, `Applied`, `Skipped`, `Saved`, `Interview`, `Rejected`, `Closed`. Optionally re-export CSV with `--export-csv-only`.

## Layout

```
data/
  jobs.sqlite
  jobs.csv
  github_sources.yml
  companies.yml
  agent_findings/
  notifications/
src/
  main.py
  ui_app.py
  ui/static/
scripts/
  run_scout.sh
  ui.sh
docs/AGENT_RUNBOOK.md
```
