#!/usr/bin/env bash
# Local jobs UI — live reads from data/jobs.sqlite
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -d .venv ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

python -m pip install -q -r requirements.txt

PORT="${PORT:-8787}"
echo "W27 UI → http://127.0.0.1:${PORT}"
exec python -m uvicorn src.ui_app:app --reload --host 127.0.0.1 --port "$PORT"
