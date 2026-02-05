#!/usr/bin/env bash
# Milestone 5: A/B test batching window (0 vs 20 vs 50 ms).
#
# Prerequisites: vLLM worker running (./scripts/run_vllm_worker.sh)
#
# Usage:
#   ./scripts/run_batch_abtest.sh
#
# Runs load test 3 times: window=0, 20, 50 ms. Saves results to experiments/runs/
# and prints comparison.

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

GATEWAY_PORT="${GATEWAY_PORT:-8001}"
RUNTIME="${LOADTEST_RUNTIME:-2m}"  # Shorter for A/B test (3 runs)
OUT_DIR="${LOADTEST_OUT_DIR:-$REPO_ROOT/experiments/runs}"
mkdir -p "$OUT_DIR"

echo "M5 A/B test: Batching window 0 vs 20 vs 50 ms"
echo "  Runtime per config: $RUNTIME"
echo "  Ensure vLLM is running: ./scripts/run_vllm_worker.sh"
echo ""

for WINDOW in 0 20 50; do
  echo "--- Window ${WINDOW} ms ---"
  # Start gateway in background
  BATCH_WINDOW_MS=$WINDOW GATEWAY_PORT=$GATEWAY_PORT uvicorn scripts.gateway:app --host 0.0.0.0 --port $GATEWAY_PORT &
  GATEWAY_PID=$!
  # Wait for gateway ready
  for i in $(seq 1 10); do
    curl -s "http://localhost:${GATEWAY_PORT}/health" >/dev/null && break
    sleep 1
  done
  # Run load test
  LOADTEST_RUNTIME=$RUNTIME ./scripts/run_loadtest.sh "http://localhost:${GATEWAY_PORT}"
  kill $GATEWAY_PID 2>/dev/null || true
  wait $GATEWAY_PID 2>/dev/null || true
  sleep 2
done

echo ""
echo "Done. Compare RPS and p95 in: $OUT_DIR/locust_*_stats.csv"
echo "Guardrail: if p95 > SLO (e.g. 5s), reduce window (50->20, 20->0)."
