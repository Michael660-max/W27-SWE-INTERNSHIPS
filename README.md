# Winter / Spring 2027 SWE Internship Tracker

Automated weekday scout for Winter/Spring 2027 software internships and co-ops (Canada + US). You don’t need to run anything locally — **Cursor Automations** handle it.

**Board:** [LISTINGS.md](LISTINGS.md) (Winter 2027 Source + Apply table)  
**Database:** `data/jobs.sqlite` (full history)  
**Alerts:** Discord summary when new valid roles are inserted

## Cron jobs (America/Toronto)

| Automation | When | Cron (EDT) | Cron (EST) |
|------------|------|------------|------------|
| **W27 Midday Scout** | Weekdays **12:30** | `30 16 * * 1-5` | `30 17 * * 1-5` |
| **W27 Evening Scout** | Weekdays **18:00** | `0 22 * * 1-5` | `0 23 * * 1-5` |

After daylight saving ends, use the EST column (+1 hour UTC).

Both jobs run on `main` in this repo. Secret required: `DISCORD_WEBHOOK_URL`.

## What each run does

Every midday and evening scout runs **both** layers, then commits updates:

1. **Layer 1 — scrape**  
   Simplify off-season list, GitHub internship lists, and company ATS boards (`data/companies.yml` + watchlist). Dedupes into SQLite, verifies apply links, refreshes [LISTINGS.md](LISTINGS.md).

2. **Layer 2 — discover (hardened)**  
   Must browse **Indeed + ATS `site:` search** (DuckDuckGo if Google captchas). LinkedIn is skipped on Cloud Automations (login always blocks). Store **official** apply URLs only.

3. **Notify**  
   Discord only for **newly inserted** Open roles with a real apply URL. Short summary with tiers (apply now / good lead / late discovery / needs verification) + link to LISTINGS. No alert when nothing new.

4. **Continue from last live run**  
   Fresh vs Late labeling uses the last successful **live** scout finish time (dry-runs don’t move the window).

5. **Commit**  
   Pushes updated `data/`, `LISTINGS.md`, findings, and coverage logs back to the repo.

## Where to look

| Output | Purpose |
|--------|---------|
| [LISTINGS.md](LISTINGS.md) | Human-readable Winter 2027 board |
| Discord | “N new roles this run” + tier counts |
| `data/jobs.sqlite` | Source of truth |
| `data/coverage/` | Which scrapers failed / returned zero |
| `data/quarantine` (in SQLite) | Unclear / failed / likely-duplicate candidates |

Automation prompt and schedule details: [docs/AUTOMATION_PROMPT.md](docs/AUTOMATION_PROMPT.md).
