#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

fail=0

if git ls-files --error-unmatch .env >/dev/null 2>&1; then
  echo "[FAIL] .env is tracked"
  fail=1
fi

tracked_bad_files="$(git ls-files '*.sqlite3' '*.db' '*.log' '.local/*' 2>/dev/null || true)"
if [[ -n "$tracked_bad_files" ]]; then
  echo "[FAIL] private runtime files are tracked:"
  echo "$tracked_bad_files"
  fail=1
fi

if rg -n 'TELEGRAM_BOT_TOKEN=[^{$[:space:]][^[:space:]]*|DARCHIVE_.*SECRET=[^{$[:space:]][^[:space:]]*|CODEX_API_KEY=[^{$[:space:]][^[:space:]]*' . \
  --glob '!.env.example' \
  --glob '!scripts/preflight_public.sh' >/tmp/darchivebot-preflight-secrets.txt; then
  echo "[FAIL] possible committed secrets found:"
  cat /tmp/darchivebot-preflight-secrets.txt
  fail=1
fi

if rg -n '/Users/hennei/.+\.local|telegram_rooms\.json.+darchive_chat_id' . \
  --glob '!scripts/preflight_public.sh' \
  --glob '!README.md' \
  --glob '!docs/architecture.md' >/tmp/darchivebot-preflight-private-paths.txt; then
  echo "[FAIL] possible private runtime coupling found:"
  cat /tmp/darchivebot-preflight-private-paths.txt
  fail=1
fi

if [[ "$fail" -ne 0 ]]; then
  exit "$fail"
fi

echo "[OK] public preflight passed"
