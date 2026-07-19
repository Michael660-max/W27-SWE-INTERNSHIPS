#!/usr/bin/env bash
# Used by Cursor Automations / local scout runs.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -d .venv ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

python -m pip install -q -r requirements.txt

if [[ -n "${DISCORD_WEBHOOK_URL:-}" ]]; then
  python src/main.py
else
  echo "DISCORD_WEBHOOK_URL unset — running with --dry-run (file notifications only)"
  python src/main.py --dry-run
fi

echo "Scout complete. DB: data/jobs.sqlite CSV: data/jobs.csv LISTINGS.md"
