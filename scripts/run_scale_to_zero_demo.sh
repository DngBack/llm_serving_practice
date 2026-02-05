#!/usr/bin/env bash
# Scale-to-zero demo (M6): idle → worker stops → send load → worker starts.
#
# 1. Start gateway with supervisor
# 2. Send 1 request (cold start)
# 3. Wait 185s (idle > 180s) → worker stops
# 4. Send 5 requests → worker starts again (cold start)
# 5. Print cold start timing
#
# Usage: ./scripts/run_scale_to_zero_demo.sh
#
# Total time: ~4–5 minutes (mostly waiting for idle timeout).

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

GATEWAY_PORT="${GATEWAY_PORT:-8001}"
IDLE_TIMEOUT=180
WAIT_AFTER_IDLE=5  # 180 + 5 = 185s to ensure worker has stopped

echo "=== Scale-to-Zero Demo (M6) ==="
echo "  Gateway port: $GATEWAY_PORT"
echo "  Idle timeout: ${IDLE_TIMEOUT}s"
echo "  Will wait ${IDLE_TIMEOUT}s + ${WAIT_AFTER_IDLE}s for worker to stop"
echo ""

echo "Starting gateway with supervisor..."
ENABLE_SUPERVISOR=1 IDLE_TIMEOUT_SEC=$IDLE_TIMEOUT GATEWAY_PORT=$GATEWAY_PORT \
  uvicorn scripts.gateway:app --host 0.0.0.0 --port "$GATEWAY_PORT" &
GATEWAY_PID=$!

sleep 3
for i in $(seq 1 15); do
  if curl -s "http://localhost:$GATEWAY_PORT/health" >/dev/null 2>&1; then
    echo "Gateway ready"
    break
  fi
  sleep 1
done

echo ""
echo "Step 1: First request (cold start)..."
curl -s -X POST "http://localhost:$GATEWAY_PORT/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-3.5-turbo","messages":[{"role":"user","content":"Hi"}],"max_tokens":10,"temperature":0}' \
  -o /dev/null -w "  Status: %{http_code}, Time: %{time_total}s\n"

echo ""
echo "Step 2: Waiting ${IDLE_TIMEOUT}s + ${WAIT_AFTER_IDLE}s for worker to stop (idle timeout)..."
sleep $((IDLE_TIMEOUT + WAIT_AFTER_IDLE))

echo ""
echo "Step 3: Sending 5 requests (triggers worker start again)..."
for i in 1 2 3 4 5; do
  curl -s -X POST "http://localhost:$GATEWAY_PORT/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -d '{"model":"gpt-3.5-turbo","messages":[{"role":"user","content":"Hi"}],"max_tokens":10,"temperature":0}' \
    -o /dev/null -w "  Request $i: %{http_code}, %{time_total}s\n"
done

echo ""
echo "=== Demo complete ==="
echo ""

kill $GATEWAY_PID 2>/dev/null || true
echo "Gateway stopped."
