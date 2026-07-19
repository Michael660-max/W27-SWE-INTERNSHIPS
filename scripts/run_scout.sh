#!/usr/bin/env bash
# Full weekday scout: Layer 1 once → Layer 2 search pack → ingest findings.
# Discord is never sent here. Evening Automation must call:
#   python src/main.py --daily-digest
# AFTER browser discovery + ingest (aggregates midday+evening, @mentions you).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -d .venv ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

python -m pip install -q -r requirements.txt

SLOT="${SCOUT_SLOT:-midday}"
echo "Scout slot: ${SLOT} (Discord only via evening --daily-digest after Layer 2)"

# 1) Layer 1: GitHub lists + Simplify + company ATS + any pending findings
echo "=== Layer 1: scrape + upsert ==="
python src/main.py

# 2) Layer 2 helper: search pack only (no GitHub re-scrape)
echo "=== Layer 2: search pack ==="
python scripts/agent_discover.py

# Optional: agent browser discovery happens here in Automations
# (see docs/DISCOVERY_WORKFLOW.md). Findings land in data/agent_findings/*.json

# 3) Ingest any new agent findings + refresh LISTINGS (no Layer 1 re-scrape)
echo "=== Ingest findings ==="
python src/main.py --ingest-findings

echo "Scout complete. DB: data/jobs.sqlite CSV: data/jobs.csv LISTINGS.md"
if [[ "${SLOT}" == "evening" ]]; then
  echo "Next (Automation): finish Layer 2 browse → ingest → python src/main.py --daily-digest"
fi
