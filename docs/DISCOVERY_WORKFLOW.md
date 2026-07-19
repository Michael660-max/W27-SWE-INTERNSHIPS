# Layer 2 — Cursor agent discovery workflow

Layer 1 (`python src/main.py`) already scrapes Simplify, GitHub internship lists, and `data/companies.yml` ATS boards. **Do not re-fetch those READMEs or boards.**

Your job is online discovery: find Winter/Spring 2027 SWE intern/co-op roles via search, then persist only **official apply URLs**.

## Before you start

```bash
python scripts/agent_discover.py
```

This writes `data/agent_findings/_search_pack_<ts>.md` from [`data/discovery_queries.yml`](../data/discovery_queries.yml) with ready-to-open LinkedIn / Indeed / Handshake / Google URLs.

Optional (boards not already in Layer 1):

```bash
python scripts/agent_discover.py --scan-extra-ats
```

## Steps

1. Open the latest `_search_pack_*.md` and work through queries (Winter 2027 SWE intern/co-op, Canada/US, backend/frontend/platform/ML/data, etc.).
2. Browse **LinkedIn Jobs, Indeed, Handshake, Google** as **discovery channels only**.
3. For each promising listing, open the employer’s **official apply** page:
   - Greenhouse, Lever, Ashby, Workday, Rippling, or the company’s careers ATS
4. Skip roles with no reliable apply URL (do not invent links).
5. Write `data/agent_findings/<YYYYMMDDTHHMMSSZ>.json` (schema below).
6. Hand off:
   ```bash
   python src/main.py --ingest-findings [--dry-run]
   ```

## LinkedIn / aggregator policy

| Allowed | Forbidden |
|---------|-----------|
| Use LinkedIn/Indeed/Handshake to *find* roles | Store a LinkedIn/Indeed/Handshake URL as `official_url` |
| Note channel in `notes` (e.g. `linkedin_search`) | Dump LinkedIn HTML into the DB |
| Resolve redirect / “Apply on company site” to ATS | Treat aggregator pages as source of truth |

## Findings JSON schema

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
      "requires_us_citizenship": false,
      "requires_us_work_auth": false,
      "requires_export_control": false,
      "eligibility_notes": "",
      "notes": "linkedin_search"
    }
  ]
}
```

`official_url` must be the apply / ATS link. After ingest, Source shows as **Cursor Agent Monitor**.

## Include / exclude

**Include:** SWE/Developer Intern or Co-op; backend/frontend/full-stack/mobile/platform/infra/DevOps/SRE/data/ML/AI; Winter or Spring 2027 / Jan–Apr or Jan–May 2027; Canada + US.

**Exclude:** Full-time new grad; summer-only 2027 unless also Winter/Spring; closed/expired; non-software; no official apply URL.
