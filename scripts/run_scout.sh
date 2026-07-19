#!/usr/bin/env bash
# Full weekday scout: Layer 1 once → Layer 2 search pack → ingest findings.
# Cursor Automations should browse the search pack / DISCOVERY_WORKFLOW after step 2
# and write data/agent_findings/<ts>.json before step 3 (or between steps).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -d .venv ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

python -m pip install -q -r requirements.txt

DRY_FLAG=()
if [[ -z "${DISCORD_WEBHOOK_URL:-}" ]]; then
  echo "DISCORD_WEBHOOK_URL unset — using --dry-run (skip Discord; still record runs)"
  DRY_FLAG=(--dry-run)
fi

# 1) Layer 1: GitHub lists + Simplify + company ATS + any pending findings
echo "=== Layer 1: scrape + upsert ==="
python src/main.py "${DRY_FLAG[@]}"

# 2) Layer 2 helper: search pack only (no GitHub re-scrape)
echo "=== Layer 2: search pack ==="
python scripts/agent_discover.py

# Optional: agent browser discovery happens here in Automations
# (see docs/DISCOVERY_WORKFLOW.md). Findings land in data/agent_findings/*.json

# 3) Ingest any new agent findings + refresh LISTINGS (no Layer 1 re-scrape)
echo "=== Ingest findings ==="
python src/main.py --ingest-findings "${DRY_FLAG[@]}"

echo "Scout complete. DB: data/jobs.sqlite CSV: data/jobs.csv LISTINGS.md"
