# Winter / Spring 2027 SWE Internship Tracker

Deterministic Layer 1 scrapers + Cursor-agent Layer 2 discovery for Winter/Spring 2027 software internships and co-ops (Canada + US). Results land in SQLite; Discord alerts only on **new inserts**.

**Source of truth:** `data/jobs.sqlite`  
**Human view:** **[LISTINGS.md](LISTINGS.md)** (Winter 2027–filtered Source + Apply table) · UI (`bash scripts/ui.sh`) · `data/jobs.csv`  
**Scheduler:** Cursor Automations — [docs/AGENT_RUNBOOK.md](docs/AGENT_RUNBOOK.md) · discovery steps: [docs/DISCOVERY_WORKFLOW.md](docs/DISCOVERY_WORKFLOW.md)

## How to use (end-to-end)

| Command | When |
|---------|------|
| `bash scripts/run_scout.sh` | Full weekday scout: Layer 1 once → search pack → ingest findings. Uses `--dry-run` if no Discord webhook. |
| `python src/main.py --dry-run` | Layer 1 + pending findings; no Discord; **still records a `runs` row** so the next window continues from this finish time. |
| `python src/main.py` | Same as above, with Discord for new inserts. |
| Agent discovery | Follow [docs/DISCOVERY_WORKFLOW.md](docs/DISCOVERY_WORKFLOW.md). Do **not** re-scrape GitHub lists. |
| `python scripts/agent_discover.py` | Emit search-pack markdown (LinkedIn/Indeed/Handshake/Google URLs). Optional `--scan-extra-ats`. |
| `python src/main.py --ingest-findings` | Merge agent JSON after discovery (no Layer 1 re-scrape). |
| `python src/main.py --export-listings-only` | Refresh Winter 2027 [LISTINGS.md](LISTINGS.md) only. |
| `bash scripts/ui.sh` | Local browse UI → http://127.0.0.1:8787 |

`LISTINGS.md` is Winter 2027–filtered. SQLite keeps full history. Discord alerts are short and link to LISTINGS.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Layer 1 only (advances last-run window; no Discord)
python src/main.py --dry-run

# Full scout helper (Layer 1 → search pack → ingest)
bash scripts/run_scout.sh

# After browsing per DISCOVERY_WORKFLOW.md and writing findings JSON:
python src/main.py --ingest-findings --dry-run

bash scripts/ui.sh
```

### Other CLI flags

| Command | Purpose |
|---------|---------|
| `python src/main.py --skip-ats` | Skip company career boards in Layer 1 |
| `python src/main.py --export-csv-only` | Rebuild CSV from SQLite |
| `python src/main.py --notify-test [N]` | Discord smoke test |

## Architecture

Twice on weekdays (12:30 & 18:00 Toronto), each Automation runs **both** layers:

1. **Layer 1** — Simplify, GitHub lists, `companies.yml` ATS (once per run; no double scrape).
2. **Layer 2** — Browser discovery (LinkedIn / aggregators / Google) → official apply URLs → `agent_findings/*.json`.
3. **Notify** — Discord only for new valid inserts; ranked by freshness, fit, location, company, eligibility.

## Freshness (“pick up from last run”)

Each pipeline run writes a `runs` row. The next Fresh vs Late window uses **last live `finished_at` − 2h** only — **dry-runs do not advance the window** (safe for testing). If no live run exists, code falls back to midday/evening schedule slots (America/Toronto).

`--dry-run` skips Discord; still scrapes/upserts/exports and records a `dry_run` row.

## Reliability upgrades

| Feature | Where |
|---------|--------|
| Source coverage logs | `data/coverage/*.json` + `source_coverage` table (ok/error/timeout/zero) |
| Quarantine | `quarantine` table — term unclear, bad HTTP, likely duplicate, filter rejects |
| Company watchlist | `data/watchlist.yml` (flagged in ATS coverage + apply-now tier) |
| Official URL priority | ATS/job URL wins over Simplify/LinkedIn on merge |
| Close only after 2 fails | `verify_fail_count` → `Closed` after 2 failed checks |
| Duplicate confidence | `exact` / `likely` / `possible` — fuzzy never auto-dropped |
| Alert tiers | Discord summary: apply now · good lead · late discovery · needs verification |

## Listings board

[LISTINGS.md](LISTINGS.md) regenerates every scout, filtered to Winter 2027:

| Column | Meaning |
|--------|---------|
| Company / Role / Location / Term / Posted | Role identity |
| **Source** | Simplify, SpeedyApply, ATS, Cursor Agent Monitor, … |
| **Apply** | Official/ATS apply link; `—` if only a homepage was available |

## GitHub sources

Configured in [`data/github_sources.yml`](data/github_sources.yml). Layer 1 only — Layer 2 must not re-fetch these READMEs.

## Schedule (America/Toronto) — both layers twice daily

| Automation | Toronto | Cron (EDT) | Layers |
|------------|---------|------------|--------|
| W27 Midday Scout | Weekdays **12:30** | `30 16 * * 1-5` | Layer 1 + Layer 2 |
| W27 Evening Scout | Weekdays **18:00** | `0 22 * * 1-5` | Layer 1 + Layer 2 |

Paste-ready prompt: [docs/AUTOMATION_PROMPT.md](docs/AUTOMATION_PROMPT.md). Flow: `bash scripts/run_scout.sh` → browser discovery per [DISCOVERY_WORKFLOW](docs/DISCOVERY_WORKFLOW.md) → ingest → commit. Set `DISCORD_WEBHOOK_URL` as a Cloud Agent secret. After DST, shift cron +1h (EST).

## Discord notifications

- **Only** newly inserted **valid** roles (`Open` + real apply URL). Updates never alert.
- Discord is a **short summary** (e.g. “18 new roles this run”) + link to LISTINGS — details stay on the board.
- Board ranking: freshness → posting time → fit → location → company → eligibility.
- Audit files: `data/notifications/` (full markdown tables for the run).

## Application tracking

UI applied-status dropdown: `Not applied`, `Applied`, `Skipped`, `Saved`, `Interview`, `Rejected`, `Closed`.

## Layout

```
data/
  jobs.sqlite
  jobs.csv
  github_sources.yml
  companies.yml
  discovery_queries.yml
  agent_findings/
  notifications/
src/
  main.py
  freshness.py
  ui_app.py
scripts/
  run_scout.sh
  agent_discover.py
  ui.sh
docs/
  AGENT_RUNBOOK.md
  DISCOVERY_WORKFLOW.md
LISTINGS.md
```
