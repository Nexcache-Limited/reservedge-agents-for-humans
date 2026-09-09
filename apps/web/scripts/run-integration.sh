#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
API_BASE="${ITAA_API_BASE:-http://127.0.0.1:8010}"
STARTED=0
if ! curl -sf "${API_BASE}/healthz" >/dev/null; then
  echo "Starting isolated G1-04 FastAPI at ${API_BASE}"
  (cd "$ROOT" && uv run uvicorn itaa_api.app:app --app-dir apps/api/src --host 127.0.0.1 --port 8010) >/tmp/itaa-g104-api.log 2>&1 &
  STARTED=$!
  trap 'if [ "$STARTED" != "0" ]; then kill "$STARTED" >/dev/null 2>&1 || true; fi' EXIT
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
    if curl -sf "${API_BASE}/healthz" >/dev/null; then
      break
    fi
    sleep 1
  done
  if ! curl -sf "${API_BASE}/healthz" >/dev/null; then
    echo "FAIL: isolated G1-04 FastAPI did not become ready. See /tmp/itaa-g104-api.log"
    exit 1
  fi
fi
cd "$ROOT"
export ITAA_API_BASE="${API_BASE}"
pnpm --filter @itaa/web test:integration
