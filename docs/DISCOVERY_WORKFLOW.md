# Layer 2 — hardened portal discovery

Layer 1 already scrapes Simplify, GitHub lists, and `companies.yml`. **Do not re-fetch those.**

Layer 2 uses **Indeed + ATS web search** as the real portal path. Persist only **official apply URLs**.

## LinkedIn on Cloud Automations

**Skip it.** Login/captcha almost always blocks Cloud Agents. LinkedIn Premium does not help.  
Do not spend the run on LinkedIn. Rely on Indeed + `site:` ATS search (Google or DuckDuckGo).

LinkedIn is only useful if you later run a **local** agent while already logged in, or via **job-alert emails** (future).

## Before you start

```bash
python scripts/agent_discover.py
```

Search pack includes exact quoted queries, per-ATS `site:` queries, and a checklist.

## Mandatory every run

| Portal | Expectation |
|--------|-------------|
| **Indeed** | ≥3 exact-query links. Prefer “Apply on company site”. |
| **Google ATS or DuckDuckGo ATS** | ≥3 `site:` ATS searches. DuckDuckGo if Google captchas. |
| LinkedIn / Handshake | **Optional — skip on Cloud Automations.** |

**Failure mode to avoid:** regenerating the search pack and stopping without browsing Indeed + ATS search.

## Steps

1. Open latest `_search_pack_*.md`.
2. Indeed → ATS site search (required).
3. For each hit, open official apply (Greenhouse / Lever / Ashby / Workday / Rippling).
4. Skip roles with no reliable apply URL.
5. Write findings JSON with `portals_attempted` (e.g. `["indeed", "duckduckgo_ats"]`).
6. `python src/main.py --ingest-findings`
7. Evening: `python src/main.py --daily-digest`

## Aggregator policy

| Allowed | Forbidden |
|---------|-----------|
| Use Indeed/Google to *find* roles | Store Indeed/LinkedIn/Handshake as `official_url` |
| Note channel in `notes` (`indeed_search`, `google_ats`, …) | Dump portal HTML into the DB |

## Findings JSON schema

```json
{
  "source": "Cursor Agent Monitor",
  "generated_at": "2027-01-15T17:30:00Z",
  "discovery": "layer2_hardened_portals",
  "portals_attempted": ["indeed", "duckduckgo_ats"],
  "portals_blocked": [],
  "jobs": [
    {
      "company": "Example",
      "exact_role_title": "Software Engineer Intern",
      "location": "Toronto, ON, Canada",
      "term": "Winter 2027",
      "posting_date": "2027-01-14",
      "official_url": "https://boards.greenhouse.io/example/jobs/123",
      "notes": "indeed_search"
    }
  ]
}
```

## Include / exclude

**Include:** SWE/Developer Intern or Co-op; Winter/Spring 2027; Canada + US.  
**Exclude:** New grad FT; summer-only; closed; no official apply URL.
