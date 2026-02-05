#!/usr/bin/env bash
# Milestone 5 + 6 + 7: Gateway (batching, scale-to-zero, admission, degradation).
#
# Without ENABLE_SUPERVISOR: vLLM must be running (./scripts/run_vllm_worker.sh).
# With ENABLE_SUPERVISOR=1: gateway starts/stops vLLM automatically (scale-to-zero).
#
# Usage:
#   ./scripts/run_gateway.sh                    # M5 only, no batching
#   BATCH_WINDOW_MS=20 ./scripts/run_gateway.sh
#   ENABLE_SUPERVISOR=1 ./scripts/run_gateway.sh # M6 scale-to-zero (no need to run vLLM first)
#   Q_MAX=64 ./scripts/run_gateway.sh            # M7 admission limit
#
# Env:
#   BATCH_WINDOW_MS   Delay before forwarding (0, 20, 50)
#   VLLM_URL          vLLM worker URL (default http://localhost:8000)
#   GATEWAY_PORT      Gateway port (default 8001)
#   ENABLE_SUPERVISOR 1 = scale-to-zero (start worker on demand, stop after idle)
#   IDLE_TIMEOUT_SEC  Idle seconds before stopping worker (default 180)
#   Q_MAX             Max queue depth before 429 (default 128)
#
# Load test: ./scripts/run_loadtest.sh http://localhost:8001

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

BATCH_WINDOW_MS="${BATCH_WINDOW_MS:-0}"
GATEWAY_PORT="${GATEWAY_PORT:-8001}"
ENABLE_SUPERVISOR="${ENABLE_SUPERVISOR:-0}"
IDLE_TIMEOUT_SEC="${IDLE_TIMEOUT_SEC:-180}"
Q_MAX="${Q_MAX:-128}"

echo "Starting gateway (M5+M6+M7)"
echo "  Batch window: ${BATCH_WINDOW_MS} ms"
echo "  Port: ${GATEWAY_PORT}"
echo "  vLLM: ${VLLM_URL:-http://localhost:8000}"
echo "  Supervisor (scale-to-zero): ${ENABLE_SUPERVISOR}"
[ "$ENABLE_SUPERVISOR" = "1" ] && echo "  Idle timeout: ${IDLE_TIMEOUT_SEC}s"
echo "  Q_MAX (admission): ${Q_MAX}"
echo ""
echo "Load test: ./scripts/run_loadtest.sh http://localhost:${GATEWAY_PORT}"
echo ""

export BATCH_WINDOW_MS
export GATEWAY_PORT
export VLLM_URL="${VLLM_URL:-http://localhost:8000}"
export ENABLE_SUPERVISOR
export IDLE_TIMEOUT_SEC
export Q_MAX

uvicorn scripts.gateway:app --host 0.0.0.0 --port "${GATEWAY_PORT}"
