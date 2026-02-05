#!/usr/bin/env bash
# Milestone 2: Run load test (fixed 200/200) and collect RPS, p50/p95, error rate.
# Requires: vLLM server running (e.g. ./scripts/run_vllm_worker.sh), and locust installed.
#
# Usage:
#   ./scripts/run_loadtest.sh [BASE_URL]
#   ./scripts/run_loadtest.sh http://localhost:8000
#
# Env overrides:
#   LOADTEST_USERS=20     number of users (when not using ramp shape)
#   LOADTEST_SPAWN_RATE=2 users spawned per second
#   LOADTEST_RUNTIME=10m  run duration (e.g. 1m, 10m)
#   USE_RAMP_SHAPE=1      use ramp-up then constant shape (see loadtest/README.md)
#   LOADTEST_OUT_DIR=     dir for CSV/HTML reports (default: experiments/runs)

set -e

BASE_URL="${1:-http://localhost:8000}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

USERS="${LOADTEST_USERS:-20}"
SPAWN_RATE="${LOADTEST_SPAWN_RATE:-2}"
RUNTIME="${LOADTEST_RUNTIME:-10m}"
OUT_DIR="${LOADTEST_OUT_DIR:-$REPO_ROOT/experiments/runs}"

mkdir -p "$OUT_DIR"
TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)
CSV_PREFIX="$OUT_DIR/locust_${TIMESTAMP}"

echo "Load test (Milestone 2) — fixed 200/200"
echo "  Base URL:   $BASE_URL"
echo "  Users:      $USERS"
echo "  Spawn rate: $SPAWN_RATE/s"
echo "  Run time:   $RUNTIME"
echo "  Reports:    ${CSV_PREFIX}_*.csv"
echo ""

if [ -n "${USE_RAMP_SHAPE}" ]; then
  echo "  Using ramp-up shape (USE_RAMP_SHAPE=$USE_RAMP_SHAPE)"
  export USE_RAMP_SHAPE
  USER_ARGS="--headless --run-time $RUNTIME"
else
  USER_ARGS="--headless -u $USERS -r $SPAWN_RATE --run-time $RUNTIME"
fi

cd loadtest
locust -f locustfile.py \
  --host="$BASE_URL" \
  $USER_ARGS \
  --csv="$CSV_PREFIX" \
  --html="${CSV_PREFIX}_report.html" \
  --skip-log-setup

echo ""
echo "Done. Metrics (see Locust output above): RPS, p50/p95 latency, failure %."
echo "CSV: ${CSV_PREFIX}_stats.csv — HTML: ${CSV_PREFIX}_report.html"
