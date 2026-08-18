#!/usr/bin/env bash
# Regression check for app-engine/server.py against the worked example
# content pack. Run this after touching server.py before committing.
set -euo pipefail

ENGINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../app-engine" && pwd)"
PORT=8799
BASE="http://127.0.0.1:${PORT}"
FAIL=0

cd "$ENGINE_DIR"
cp content/example_content.json content/content.json
rm -f content/progress.json

cleanup() {
  kill "$SERVER_PID" >/dev/null 2>&1 || true
  rm -f content/content.json content/progress.json
}
trap cleanup EXIT

python3 server.py "$PORT" > /tmp/book-to-lab-test-server.log 2>&1 &
SERVER_PID=$!
sleep 1

check() {
  local desc="$1" expected="$2" actual="$3"
  if [[ "$actual" == *"$expected"* ]]; then
    echo "ok   - $desc"
  else
    echo "FAIL - $desc"
    echo "       expected to contain: $expected"
    echo "       got: $actual"
    FAIL=1
  fi
}

# 1. content loads, first blob available, second locked
resp=$(curl -s "$BASE/api/content")
check "first blob available" '"ch01-b01": {"status": "available"' "$resp"
check "second blob locked"   '"ch01-b02": {"status": "locked"'    "$resp"

# 2. wrong submission fails and does not unlock next blob
resp=$(curl -s -X POST "$BASE/api/submit" -H 'Content-Type: application/json' \
  -d '{"blob_id":"ch01-b01","code":"def linear_search(items, target):\n    return -999\n"}')
check "wrong solution fails" '"passed": false' "$resp"

# 3. locked blob rejects submission server-side
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/submit" \
  -H 'Content-Type: application/json' -d '{"blob_id":"ch01-b02","code":"x"}')
check "locked blob submission returns 403" "403" "$code"

# 4. correct submission passes and unlocks next blob
resp=$(curl -s -X POST "$BASE/api/submit" -H 'Content-Type: application/json' \
  -d '{"blob_id":"ch01-b01","code":"def linear_search(items, target):\n    for i, v in enumerate(items):\n        if v == target:\n            return i\n    return -1\n"}')
check "correct solution passes" '"passed": true' "$resp"

# 4b. submission is persisted as a draft
resp=$(curl -s "$BASE/api/content")
check "draft saved after submit" '"draft": "def linear_search' "$resp"

# 4c. struggled pass (failed once, then passed) stays at box 1 rather than
# advancing, so it comes back for review sooner than an easy first-try pass
check "struggled pass keeps box at 1" '"ch01-b01": {"status": "passed", "box": 1' "$resp"

# 4c. explicit draft save (in-progress, not-yet-submitted code) persists
curl -s -X POST "$BASE/api/save-draft" -H 'Content-Type: application/json' \
  -d '{"blob_id":"ch01-b02","code":"# work in progress"}' > /dev/null
resp=$(curl -s "$BASE/api/content")
check "explicit draft save persists" '"draft": "# work in progress"' "$resp"

resp=$(curl -s "$BASE/api/content")
check "next blob unlocked after passing" '"ch01-b02": {"status": "available"' "$resp"

# 5. hints return in order
resp=$(curl -s -X POST "$BASE/api/hint" -H 'Content-Type: application/json' \
  -d '{"blob_id":"ch01-b02","level":0}')
check "hint 0 returned" '"total_hints": 3' "$resp"

# 6. knowledge graph traverses prerequisites
resp=$(curl -s "$BASE/api/graph?blob_id=ch01-b03&depth=4")
check "graph includes root" '"id": "ch01-b03"' "$resp"
check "graph includes prerequisite" '"id": "ch01-b01"' "$resp"

# 7. skip enforces gating too - locked blob can't be skipped
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/skip" \
  -H 'Content-Type: application/json' -d '{"blob_id":"ch01-b03"}')
check "locked blob skip returns 403" "403" "$code"

# skip marks a blob passed without solving it, and unlocks the next one
resp=$(curl -s -X POST "$BASE/api/skip" -H 'Content-Type: application/json' \
  -d '{"blob_id":"ch01-b02"}')
check "skip accepted" '"ok": true' "$resp"
resp=$(curl -s "$BASE/api/content")
check "skipped blob marked passed+skipped" '"ch01-b02": {"status": "passed"' "$resp"
check "skipped flag recorded" '"skipped": true' "$resp"
check "next blob unlocked after skip" '"ch01-b03": {"status": "available"' "$resp"
# an easy (non-struggled) pass advances the box normally, unlike the
# struggled first-try-failed case above which stayed at 1
check "unstruggled skip advances box past 1" '"ch01-b02": {"status": "passed", "box": 2' "$resp"

# 8. short-answer self-assessment updates progress
resp=$(curl -s -X POST "$BASE/api/self-assess" -H 'Content-Type: application/json' \
  -d '{"blob_id":"ch01-b03","correct":true}')
check "self-assess accepted" '"ok": true' "$resp"

# 9. static frontend served
code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/")
check "index.html served" "200" "$code"

# 10. reset wipes all progress back to the initial state
resp=$(curl -s -X POST "$BASE/api/reset")
check "reset accepted" '"ok": true' "$resp"
resp=$(curl -s "$BASE/api/content")
check "reset clears passed status" '"ch01-b01": {"status": "available"' "$resp"
check "reset relocks later blobs" '"ch01-b03": {"status": "locked"' "$resp"

# 11. shutdown responds first, then the process actually exits shortly after
resp=$(curl -s -X POST "$BASE/api/shutdown")
check "shutdown accepted" '"ok": true' "$resp"
sleep 1
if curl -s -o /dev/null --max-time 1 "$BASE/api/content"; then
  echo "FAIL - server still responding after shutdown"
  FAIL=1
else
  echo "ok   - server process exited after shutdown"
fi

if [[ "$FAIL" -eq 0 ]]; then
  echo
  echo "All checks passed."
else
  echo
  echo "Some checks FAILED - see above."
  exit 1
fi
