# Cursor Agent Runbook — W27 Internship Scout

Instruction body for **W27 Midday Scout** and **W27 Evening Scout** Cursor Automations.  
Copy-paste prompt: [AUTOMATION_PROMPT.md](AUTOMATION_PROMPT.md). Discovery steps: [DISCOVERY_WORKFLOW.md](DISCOVERY_WORKFLOW.md).

## Schedule (both layers every run)

| Automation | America/Toronto | Cron (EDT / UTC) | Cron (EST / UTC) |
|------------|-----------------|------------------|------------------|
| W27 Midday Scout | Weekdays **12:30** | `30 16 * * 1-5` | `30 17 * * 1-5` |
| W27 Evening Scout | Weekdays **18:00** | `0 22 * * 1-5` | `0 23 * * 1-5` |

Each run executes **Layer 1** (lists + ATS) **and Layer 2** (browser discovery). Freshness uses last finished pipeline run (`runs.finished_at` − 2h); schedule slots are fallback only.

## Goal

Find Winter 2027 / Spring 2027 software internships and co-ops (Canada + US). Persist in SQLite. Discord only for newly inserted **valid** roles. Commit tracker outputs. **Do not double-scrape GitHub lists.**

## Steps (every run)

1. Checkout `main` and pull latest.
2. `pip install -r requirements.txt`
3. Orchestrate Layer 1 + search pack + pending ingest:
   ```bash
   bash scripts/run_scout.sh
   ```
4. **Layer 2 browser discovery** (required every weekday run):
   - Follow [DISCOVERY_WORKFLOW.md](DISCOVERY_WORKFLOW.md).
   - Open latest `data/agent_findings/_search_pack_*.md`.
   - Browse LinkedIn / Indeed / Handshake / Google as discovery only.
   - Resolve official apply URLs only; never store aggregator URLs as `official_url`.
   - Write `data/agent_findings/YYYYMMDDTHHMMSSZ.json`.
5. Ingest after writing findings (if not already covered):
   ```bash
   python src/main.py --ingest-findings
   ```
6. Confirm `data/jobs.sqlite`, `data/jobs.csv`, and `LISTINGS.md` updated.
7. Commit/push tracker outputs only (never secrets).
8. Zero new roles is success.

## Notifications

| Rule | Behavior |
|------|----------|
| When | Only **newly inserted** roles in this run |
| Valid | `status=Open` **and** a real apply URL (ATS/job page) |
| Skip | Updates, Unverified, Closed, homepage-only links |
| Format | Short summary only (e.g. “18 new roles this run”) + LISTINGS link |
| Rank | LISTINGS / CSV: freshness → posting time → fit → location → company → eligibility |
| Board | Winter 2027 [LISTINGS.md](../LISTINGS.md) holds the full Source + Apply table |

## Priority scoring

`priority_score` / `sort_jobs` combine:

1. **Freshness** — Fresh vs Late; recent posting age boosts  
2. **Fit** — SWE / backend / full-stack / platform / infra / ML / data  
3. **Location** — Canada and Canada-remote first  
4. **Company quality** — known high-signal employers  
5. **Eligibility** — citizenship / export-control / no-sponsorship penalties  

## Environment

- `DISCORD_WEBHOOK_URL` — Cloud Agent secret; never commit  
- Local UI: `bash scripts/ui.sh`  
- Smoke test: `python src/main.py --notify-test 3`
