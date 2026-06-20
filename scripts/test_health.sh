#!/usr/bin/env bash
#
# Smoke test for healthchecks + rate limiting.
#
# Usage:
#   scripts/test_health.sh [BASE_URL]
#
# Examples:
#   scripts/test_health.sh                       # defaults to http://localhost:8000
#   scripts/test_health.sh https://example.com
#
set -uo pipefail

BASE_URL="${1:-http://localhost:8000}"
PASS=0
FAIL=0

green() { printf "\033[32m%s\033[0m\n" "$1"; }
red()   { printf "\033[31m%s\033[0m\n" "$1"; }
bold()  { printf "\033[1m%s\033[0m\n" "$1"; }

check_status() {
  local label="$1" url="$2" expected="$3"
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' "$url")"
  if [ "$code" = "$expected" ]; then
    green "  PASS  $label -> $code"
    PASS=$((PASS + 1))
  else
    red "  FAIL  $label -> $code (expected $expected)"
    FAIL=$((FAIL + 1))
  fi
}

bold "== Healthchecks ($BASE_URL) =="
echo "GET /health";       curl -s "$BASE_URL/health";       echo
echo "GET /health/live";  curl -s "$BASE_URL/health/live";  echo
echo "GET /health/ready"; curl -s "$BASE_URL/health/ready"; echo
echo

bold "== Health status codes =="
check_status "/health"       "$BASE_URL/health"       "200"
check_status "/health/live"  "$BASE_URL/health/live"  "200"
# /ready may be 200 (all deps up) or 503 (a dep down); accept either as a valid response.
ready_code="$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/health/ready")"
if [ "$ready_code" = "200" ] || [ "$ready_code" = "503" ]; then
  green "  PASS  /health/ready -> $ready_code"
  PASS=$((PASS + 1))
else
  red "  FAIL  /health/ready -> $ready_code (expected 200 or 503)"
  FAIL=$((FAIL + 1))
fi
echo

bold "== Rate limiting: 11x POST /api/auth/login (limit 10/min) =="
last_code=""
for i in $(seq 1 11); do
  last_code="$(curl -s -o /dev/null -w '%{http_code}' \
    -X POST "$BASE_URL/api/auth/login" \
    -H 'Content-Type: application/json' \
    -d '{"email":"ratelimit-test@example.com","password":"wrong-password"}')"
  echo "  request #$i -> $last_code"
done

if [ "$last_code" = "429" ]; then
  green "  PASS  11th request returned 429 Too Many Requests"
  PASS=$((PASS + 1))
else
  red "  FAIL  11th request returned $last_code (expected 429)"
  red "        (is RATE_LIMIT_ENABLED=true and Redis reachable?)"
  FAIL=$((FAIL + 1))
fi
echo

bold "== Summary =="
green "  Passed: $PASS"
if [ "$FAIL" -gt 0 ]; then
  red "  Failed: $FAIL"
  exit 1
fi
echo "  All checks passed."
