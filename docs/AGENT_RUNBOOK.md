# Cursor Agent Runbook — W27 Internship Scout

Use this as the instruction body for the **W27 Midday Scout** and **W27 Evening Scout** Cursor Automations.

## Schedule

| Automation | America/Toronto | Cron (EDT / UTC) | Cron (EST / UTC) |
|------------|-----------------|------------------|------------------|
| W27 Midday Scout | Weekdays 12:30 | `30 16 * * 1-5` | `30 17 * * 1-5` |
| W27 Evening Scout | Weekdays 18:00 | `0 22 * * 1-5` | `0 23 * * 1-5` |

Freshness windows are enforced in code (`America/Toronto`). Monday 12:30 looks back to Friday 18:00.

## Goal

Find Winter 2027 / Spring 2027 / January–April 2027 / January–May 2027 software internships and co-ops in Canada and the United States. Persist everything in SQLite. Notify Discord only for newly inserted valid roles. Commit DB/CSV updates to `main`.

## Steps (every run)

1. Checkout this repo on `main` and pull latest.
2. Ensure Python 3.11+ and install deps:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the deterministic pipeline (dry-run Discord if webhook unset):
   ```bash
   python src/main.py --dry-run
   ```
   If `DISCORD_WEBHOOK_URL` is set in the environment, run without `--dry-run`:
   ```bash
   python src/main.py
   ```
4. **Agent discovery (Layer 2):** Browse/search for new postings using terms such as:
   - Winter 2027 software engineer intern
   - Spring 2027 software engineering intern
   - January 2027 software intern / co-op
   - off-cycle 2027 software intern
   - backend/frontend/full stack/platform/infra/AI/data engineer intern Winter 2027  
   Prefer official employer / ATS pages (Greenhouse, Lever, Ashby, Workday, Rippling). Avoid treating LinkedIn/Indeed as source of truth.
5. Write structured findings to:
   `data/agent_findings/YYYYMMDDTHHMMSSZ.json`
   Schema:
   ```json
   {
     "source": "Cursor Agent Monitor",
     "generated_at": "2027-01-15T17:30:00Z",
     "jobs": [
       {
         "company": "Example",
         "exact_role_title": "Software Engineer Intern",
         "location": "Toronto, ON, Canada",
         "term": "Winter 2027",
         "posting_date": "2027-01-14",
         "official_url": "https://boards.greenhouse.io/example/jobs/123",
         "freshness_label": "Fresh",
         "requires_us_citizenship": false,
         "requires_us_work_auth": false,
         "requires_export_control": false,
         "eligibility_notes": "",
         "notes": ""
       }
     ]
   }
   ```
6. Ingest findings:
   ```bash
   python src/main.py --ingest-findings data/agent_findings
   ```
   (Or a full `python src/main.py` which also re-scrapes lists.)
7. Confirm `data/jobs.sqlite`, `data/jobs.csv`, and `LISTINGS.md` updated. New roles appear under `data/notifications/`.
8. Commit and push only tracker outputs and findings (never secrets):
   ```bash
   git add data/jobs.sqlite data/jobs.csv LISTINGS.md data/agent_findings data/notifications
   git status
   git commit -m "chore(data): update internship DB from scheduled scout"
   git push origin HEAD
   ```
9. Do **not** invent jobs. Do **not** rely on ChatGPT memory. SQLite is the source of truth.
10. If zero new roles, still OK to exit successfully; skip Discord (pipeline already does).

## Include / exclude

**Include:** Software Engineer/Developer Intern or Co-op; backend/frontend/full-stack/mobile/platform/infra/cloud/DevOps/SRE/data/ML/AI/embedded/firmware/security/developer-tools; CS co-op; IT software development co-op.

**Exclude:** Full-time new grad; summer-only 2027 unless also Winter/Spring; Fall 2026-only unless Winter/Spring 2027 allowed; helpdesk/BA/non-software; closed/expired; roles incompatible with returning to school.

## Notification rules

Only newly inserted roles. Discord sends a short summary linking to `LISTINGS.md` (full Source + Apply table). Sort by freshness, then posting date, then priority.

## Environment

- `DISCORD_WEBHOOK_URL` — Discord incoming webhook for alerts (set as a **Cloud Agent / Automation secret**, never commit to git)
- Local UI (not needed on cron): `bash scripts/ui.sh` → http://127.0.0.1:8787
- Discord smoke test (local): `python src/main.py --notify-test 3`
- Full board: commit `LISTINGS.md` (Company | Role | Location | Term | Posted | Source | Apply)

### Cloud Agent secret setup
1. In Cursor Automations / Cloud Agents settings, add secret `DISCORD_WEBHOOK_URL` with your webhook URL.
2. Do not put the webhook in the repo or in the automation prompt text.
