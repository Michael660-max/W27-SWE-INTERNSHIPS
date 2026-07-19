# Cursor Automation prompt — W27 twice-daily scout

Create **two** identical Automations (same instructions; different cron). Each run must execute **both Layer 1 and Layer 2**.

## Triggers (America/Toronto)

| Name | Local time | Cron while EDT | Cron while EST |
|------|------------|----------------|----------------|
| W27 Midday Scout | Weekdays 12:30 | `30 16 * * 1-5` | `30 17 * * 1-5` |
| W27 Evening Scout | Weekdays 18:00 | `0 22 * * 1-5` | `0 23 * * 1-5` |

Secret: `DISCORD_WEBHOOK_URL` (never put in the prompt).

## Instructions (paste into both Automations)

```
You are the W27 Winter/Spring 2027 SWE internship scout for this repo.

Schedule context: this Automation runs twice on weekdays (12:30 and 18:00 America/Toronto). Every run must complete BOTH layers — do not skip Layer 2.

## Layer 1 + orchestration
1. Checkout main and pull latest.
2. pip install -r requirements.txt
3. Run: bash scripts/run_scout.sh
   - This scrapes GitHub lists + Simplify + companies.yml ATS once (Layer 1).
   - Emits a Layer 2 search pack via scripts/agent_discover.py.
   - Ingests any existing agent_findings JSON.
   - Uses --dry-run automatically if DISCORD_WEBHOOK_URL is unset (still records runs).
4. Do NOT re-fetch Simplify / GitHub internship READMEs as a separate discovery scrape.

## Layer 2 — browser discovery (required every run)
Follow docs/DISCOVERY_WORKFLOW.md and data/discovery_queries.yml / the latest data/agent_findings/_search_pack_*.md:
1. Browse LinkedIn Jobs, Indeed, Handshake, and Google using the search-pack URLs (discovery only).
2. For each Winter/Spring 2027 SWE intern/co-op candidate (Canada/US), open the official apply page (Greenhouse, Lever, Ashby, Workday, Rippling, or company ATS).
3. Never store LinkedIn/Indeed/Handshake URLs as official_url.
4. Write data/agent_findings/YYYYMMDDTHHMMSSZ.json with company, title, location, term, posting_date if known, official_url (apply link), eligibility flags, and notes including the discovery channel (e.g. linkedin_search).
5. Skip roles without a reliable apply URL.
6. Ingest: python src/main.py --ingest-findings
   (omit --dry-run when DISCORD_WEBHOOK_URL is set so new valid inserts alert Discord).

## Notifications (automatic)
Discord alerts only when newly inserted Open roles with a real apply URL exist. Message is a short summary only (e.g. "18 new roles this run") plus a link to LISTINGS.md — no per-job dump in Discord. Freshness window continues from the last finished run (live or dry-run).

## Finish
- Confirm data/jobs.sqlite, data/jobs.csv, LISTINGS.md updated.
- Commit and push tracker outputs only (never secrets):
  git add data/jobs.sqlite data/jobs.csv LISTINGS.md data/agent_findings data/notifications
  git commit -m "chore(data): update internship DB from scheduled scout"
  git push origin HEAD
- Zero new roles is success. Do not invent jobs.
```

## Tools / permissions

- Shell / terminal (pip, python, git)
- Browser (Layer 2 LinkedIn / job boards / official ATS)
- Network (scrapers + Discord webhook)
- Git write on this repo
