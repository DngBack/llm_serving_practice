#!/usr/bin/env bash
# Milestone 5: Run gateway with micro-batching window.
#
# Prerequisites: vLLM worker running (./scripts/run_vllm_worker.sh)
#
# Usage:
#   ./scripts/run_gateway.sh              # BATCH_WINDOW_MS=0 (no batching)
#   BATCH_WINDOW_MS=20 ./scripts/run_gateway.sh
#   BATCH_WINDOW_MS=50 ./scripts/run_gateway.sh
#
# Env:
#   BATCH_WINDOW_MS   Delay before forwarding (0, 20, 50 for A/B test)
#   VLLM_URL          vLLM worker URL (default http://localhost:8000)
#   GATEWAY_PORT      Gateway port (default 8001)
#
# Load test against gateway: ./scripts/run_loadtest.sh http://localhost:8001

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

BATCH_WINDOW_MS="${BATCH_WINDOW_MS:-0}"
GATEWAY_PORT="${GATEWAY_PORT:-8001}"

echo "Starting gateway (M5 micro-batching)"
echo "  Batch window: ${BATCH_WINDOW_MS} ms"
echo "  Port: ${GATEWAY_PORT}"
echo "  vLLM: ${VLLM_URL:-http://localhost:8000}"
echo ""
echo "Load test: ./scripts/run_loadtest.sh http://localhost:${GATEWAY_PORT}"
echo ""

export BATCH_WINDOW_MS
export GATEWAY_PORT
export VLLM_URL="${VLLM_URL:-http://localhost:8000}"

uvicorn scripts.gateway:app --host 0.0.0.0 --port "${GATEWAY_PORT}"
