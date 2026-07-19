# Winter / Spring 2027 SWE Internship Tracker

Automated weekday scout for Winter/Spring 2027 software internships and co-ops (Canada + US). You don’t need to run anything locally — **Cursor Automations** handle it.

**Board:** [LISTINGS.md](LISTINGS.md) (Winter 2027 Source + Apply table)  
**Database:** `data/jobs.sqlite` (full history)  
**Alerts:** One Discord digest at the **evening** cron (not per-run)

## Cron jobs (America/Toronto)

| Automation | When | Cron (EDT) | Cron (EST) | Discord |
|------------|------|------------|------------|---------|
| **W27 Midday Scout** | Weekdays **12:30** | `30 16 * * 1-5` | `30 17 * * 1-5` | No — scrapes/discovers only |
| **W27 Evening Scout** | Weekdays **18:00** | `0 22 * * 1-5` | `0 23 * * 1-5` | **Yes** — daily digest + @you |

After daylight saving ends, use the EST column (+1 hour UTC).

**Secrets (Cloud Agent):**

| Secret | Purpose |
|--------|---------|
| `DISCORD_WEBHOOK_URL` | Incoming webhook |
| `DISCORD_USER_ID` | Your numeric Discord user id (Developer Mode → Copy User ID) so the evening digest `@` mentions you |

Evening automation must set env `SCOUT_SLOT=evening`. Midday can omit it (defaults to midday).

## What each run does

Both crons run **Layer 1 + Layer 2**, then commit:

1. **Layer 1 — scrape**  
   Simplify, GitHub lists, company ATS (`companies.yml` + watchlist) → SQLite → [LISTINGS.md](LISTINGS.md).

2. **Layer 2 — discover**  
   Browser search for Winter/Spring 2027 SWE intern/co-op; store official apply URLs only.

3. **Discord (evening only)**  
   After Layer 2, evening runs `python src/main.py --daily-digest`: aggregates new Open roles with apply links since the last digest (midday + evening), posts a short tier summary, **@mentions you** (`DISCORD_USER_ID`), and links LISTINGS. Midday never pings Discord.

4. **Continue from last live run**  
   Fresh vs Late uses the last live scout finish time.

5. **Commit**  
   Pushes `data/`, LISTINGS, findings, coverage logs.

## Where to look

| Output | Purpose |
|--------|---------|
| [LISTINGS.md](LISTINGS.md) | Winter 2027 board |
| Discord (18:00) | Daily digest + @mention |
| `data/jobs.sqlite` | Source of truth |
| `data/coverage/` | Scraper health |

Automation prompt: [docs/AUTOMATION_PROMPT.md](docs/AUTOMATION_PROMPT.md).
