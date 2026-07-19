# Winter / Spring 2027 SWE Internship Tracker

Deterministic scraper + SQLite database that aggregates Winter 2027 / Spring 2027 software internships and co-ops (Canada + US). Cursor Automations run twice on weekdays, scrape GitHub lists and company boards, optionally discover more roles via browsing, update the DB, commit results, and Discord-notify only **new** roles.

**Source of truth:** `data/jobs.sqlite`  
**Human view:** `data/jobs.csv`  
**Scheduler:** Cursor Automations (see [docs/AGENT_RUNBOOK.md](docs/AGENT_RUNBOOK.md))

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Full collect → verify → dedupe → notify file → CSV
python src/main.py --dry-run

# Optional: set Discord webhook
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
python src/main.py
```

### CLI

| Command | Purpose |
|---------|---------|
| `python src/main.py` | Scrape Simplify + GitHub lists + company ATS + ingest `data/agent_findings/` |
| `python src/main.py --dry-run` | Same, but do not POST to Discord |
| `python src/main.py --skip-ats` | Skip company career boards |
| `python src/main.py --ingest-findings` | Only ingest agent JSON findings |
| `python src/main.py --export-csv-only` | Rebuild CSV from SQLite |

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

Set `DISCORD_WEBHOOK_URL` in the environment used by local runs / Cloud Agents. The pipeline also writes `data/notifications/<timestamp>.md`.

## Cursor Automations (scheduled scouts)

Create two Automations (see [docs/AGENT_RUNBOOK.md](docs/AGENT_RUNBOOK.md)):

| Name | Toronto time | Cron (EDT) |
|------|--------------|------------|
| W27 Midday Scout | Weekdays 12:30 | `30 16 * * 1-5` |
| W27 Evening Scout | Weekdays 18:00 | `0 22 * * 1-5` |

Each run should: pull `main` → `bash scripts/run_scout.sh` → browse/search for new roles → write `data/agent_findings/<timestamp>.json` → `python src/main.py --ingest-findings` → commit/push `data/`.

Set `DISCORD_WEBHOOK_URL` in the Cloud Agent environment. After DST ends, shift cron +1 hour (EST).

## Application tracking

Update `applied_status` in SQLite (`Not applied`, `Applied`, `Skipped`, `Saved`, `Interview`, `Rejected`, `Closed`) as you apply. Re-export CSV with `--export-csv-only`.

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
  ...
docs/AGENT_RUNBOOK.md
```
