# Cursor Automation prompt — W27 twice-daily scout

Two Automations; each runs **Layer 1 + Layer 2**. Discord only on **evening**, after discovery.

## Triggers (America/Toronto)

| Name | Local time | Cron (EDT) | Cron (EST) | Discord |
|------|------------|------------|------------|---------|
| W27 Midday Scout | Weekdays 12:30 | `30 16 * * 1-5` | `30 17 * * 1-5` | No |
| W27 Evening Scout | Weekdays 18:00 | `0 22 * * 1-5` | `0 23 * * 1-5` | Daily digest + @you |

**Secrets:** `DISCORD_WEBHOOK_URL`, `DISCORD_USER_ID` (numeric Discord user id). Never put secrets in the prompt.

Optional env: `SCOUT_SLOT=midday` or `evening` (logging only).

## Midday instructions

```
You are the W27 Winter/Spring 2027 SWE internship scout for Michael660-max/W27-SWE-INTERNSHIPS on main.

MIDDAY (12:30 America/Toronto). Both layers. Do NOT send Discord.

1. Checkout main and pull latest.
2. pip install -r requirements.txt
3. bash scripts/run_scout.sh
4. Layer 2 browse: open latest data/agent_findings/_search_pack_*.md; search Winter/Spring 2027 SWE intern/co-op (Canada/US); official apply URLs only; write data/agent_findings/YYYYMMDDTHHMMSSZ.json; python src/main.py --ingest-findings
5. Do not re-scrape GitHub/Simplify as discovery.
6. Commit/push data/jobs.sqlite data/jobs.csv LISTINGS.md data/agent_findings data/coverage
7. Zero new roles is OK. Do not invent jobs.
```

## Evening instructions

```
You are the W27 Winter/Spring 2027 SWE internship scout for Michael660-max/W27-SWE-INTERNSHIPS on main.

EVENING (18:00 America/Toronto). Both layers, then ONE Discord digest that @mentions the user.

1. Checkout main and pull latest.
2. pip install -r requirements.txt
3. bash scripts/run_scout.sh
4. Layer 2 browse: open latest _search_pack_*.md; Winter/Spring 2027 SWE intern/co-op; official apply URLs only; write findings JSON; python src/main.py --ingest-findings
5. Daily digest (required): python src/main.py --daily-digest
   Aggregates new Open+apply roles since last digest (midday + evening), posts summary to Discord, tags DISCORD_USER_ID.
6. Do not re-scrape GitHub/Simplify as discovery.
7. Commit/push data/jobs.sqlite data/jobs.csv LISTINGS.md data/agent_findings data/coverage
8. Zero new roles is OK — digest still pings with 0. Do not invent jobs.
```

## Discord behavior

- Midday: never Discord.
- Evening: `python src/main.py --daily-digest` once after ingest — tier summary + LISTINGS + `@` you.

## Tools / permissions

- Shell, browser, network, git write on this repo
