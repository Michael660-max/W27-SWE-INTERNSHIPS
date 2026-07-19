# Cursor Automation prompt — W27 twice-daily scout

Two Automations; Layer 1 + hardened Layer 2 (**Indeed + ATS search**; skip LinkedIn on Cloud). Discord evening only.

## Triggers (America/Toronto)

| Name | Local time | Cron (EDT) | Cron (EST) | Discord |
|------|------------|------------|------------|---------|
| W27 Midday Scout | Weekdays 12:30 | `30 16 * * 1-5` | `30 17 * * 1-5` | No |
| W27 Evening Scout | Weekdays 18:00 | `0 22 * * 1-5` | `0 23 * * 1-5` | Daily digest + @you |

**Secrets:** `DISCORD_WEBHOOK_URL`, `DISCORD_USER_ID`.

---

## Midday — paste this

```
You are the W27 Winter/Spring 2027 SWE internship scout for Michael660-max/W27-SWE-INTERNSHIPS on main.

MIDDAY (12:30 America/Toronto). Layer 1 + Layer 2. Do NOT send Discord.

1. Checkout main and pull latest.
2. pip install -r requirements.txt
3. bash scripts/run_scout.sh
4. LAYER 2 (required — Indeed + ATS search; SKIP LinkedIn on Cloud):
   a. Open latest data/agent_findings/_search_pack_*.md.
   b. Indeed: open at least 3 exact-query Indeed links; use “Apply on company site” → official ATS.
   c. ATS search: open at least 3 google_ats or duckduckgo_ats site: links (Ashby/Greenhouse/Lever/Workday/Rippling). If Google captchas, use DuckDuckGo only.
   d. Do NOT spend time on LinkedIn or Handshake — Cloud Agents get login-walled. Skip them.
   e. Never store Indeed/LinkedIn URLs as official_url. Official apply links only.
   f. Write data/agent_findings/YYYYMMDDTHHMMSSZ.json with portals_attempted (e.g. indeed, duckduckgo_ats) and jobs[].
   g. python src/main.py --ingest-findings
5. Do not re-scrape GitHub/Simplify as discovery.
6. Commit/push data/jobs.sqlite data/jobs.csv LISTINGS.md data/agent_findings data/coverage
7. Empty findings only OK if you actually browsed Indeed + ATS search. Do not invent jobs.
```

---

## Evening — paste this

```
You are the W27 Winter/Spring 2027 SWE internship scout for Michael660-max/W27-SWE-INTERNSHIPS on main.

EVENING (18:00 America/Toronto). Layer 1 + Layer 2, then Discord digest @mention.

1. Checkout main and pull latest.
2. pip install -r requirements.txt
3. bash scripts/run_scout.sh
4. LAYER 2 (Indeed + ATS search; SKIP LinkedIn on Cloud):
   a. Open latest _search_pack_*.md.
   b. Indeed ≥3 exact-query searches → official ATS apply URLs.
   c. ATS site search ≥3 (DuckDuckGo if Google blocks).
   d. Skip LinkedIn/Handshake on Cloud — do not fight login.
   e. Findings JSON with portals_attempted + official_url only; then python src/main.py --ingest-findings
5. python src/main.py --daily-digest
6. Commit/push data/jobs.sqlite data/jobs.csv LISTINGS.md data/agent_findings data/coverage
7. Zero new roles OK if portals were browsed — digest still pings. Do not invent jobs.
```
