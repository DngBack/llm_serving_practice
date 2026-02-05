#!/usr/bin/env bash
# Admission test (M7): Q_MAX=10, 20 users → expect ~10 success + ~10 with 429.
#
# Simulates "max 10 requests in queue" — when 20 requests come in,
# first ~10 get through, rest get 429 (Too Many Requests).
#
# Usage: ./scripts/run_admission_test.sh
#
# Prerequisites: vLLM running (./scripts/run_vllm_worker.sh in another terminal).

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

GATEWAY_PORT="${GATEWAY_PORT:-8001}"
VLLM_URL="${VLLM_URL:-http://localhost:8000}"
Q_MAX=10
USERS=20
RUNTIME=1m

echo "=== Admission Test (M7) ==="
echo "  Q_MAX=$Q_MAX (reject when queue_depth > $Q_MAX)"
echo "  Users: $USERS"
echo "  Run time: $RUNTIME"
echo ""

# Check if vLLM is running
if ! curl -s -o /dev/null -w "%{http_code}" "$VLLM_URL/v1/models" 2>/dev/null | grep -q 200; then
  echo "ERROR: vLLM not running at $VLLM_URL"
  echo "Start it first: ./scripts/run_vllm_worker.sh"
  exit 1
fi
echo "vLLM OK at $VLLM_URL"

echo ""
echo "Starting gateway with Q_MAX=$Q_MAX on port $GATEWAY_PORT..."
Q_MAX=$Q_MAX GATEWAY_PORT=$GATEWAY_PORT VLLM_URL=$VLLM_URL \
  uvicorn scripts.gateway:app --host 0.0.0.0 --port "$GATEWAY_PORT" &
GATEWAY_PID=$!
sleep 3

for i in $(seq 1 10); do
  if curl -s "http://localhost:$GATEWAY_PORT/health" >/dev/null 2>&1; then
    echo "Gateway ready"
    break
  fi
  sleep 1
done

echo ""
echo "Running load test: $USERS users, $RUNTIME..."
OUT_DIR="$REPO_ROOT/experiments/runs"
mkdir -p "$OUT_DIR"
TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)
CSV_PREFIX="$OUT_DIR/locust_admission_${TIMESTAMP}"

cd loadtest
locust -f locustfile.py \
  --host="http://localhost:$GATEWAY_PORT" \
  --headless -u "$USERS" -r 5 --run-time "$RUNTIME" \
  --csv="$CSV_PREFIX" \
  --html="${CSV_PREFIX}_report.html" \
  --skip-log-setup 2>&1 | tee /tmp/locust_admission.log

cd "$REPO_ROOT"

kill $GATEWAY_PID 2>/dev/null || true

echo ""
echo "=== Summary ==="
echo "  Report: ${CSV_PREFIX}_report.html"
echo "  Expect: Some 429 failures when Q_MAX=10 and users=20"
echo "  Open HTML to see failure type (429 Too Many Requests)"
