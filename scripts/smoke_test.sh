#!/usr/bin/env bash
# Milestone 1: One request end-to-end (functional smoke test).
# Requires vLLM server running (e.g. ./scripts/run_vllm_worker.sh).
# Usage: ./scripts/smoke_test.sh [BASE_URL]

set -e

BASE_URL="${1:-http://localhost:8000}"
ENDPOINT="${BASE_URL}/v1/chat/completions"

echo "Smoke test: one request to vLLM"
echo "  Endpoint: ${ENDPOINT}"
echo ""

# Wait for server to be ready (OpenAI-compatible /v1/models)
max_attempts=60
attempt=0
while ! curl -sf -o /dev/null "${BASE_URL}/v1/models" 2>/dev/null; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge "$max_attempts" ]; then
    echo "Error: Server at ${BASE_URL} did not become ready in time."
    exit 1
  fi
  echo "  Waiting for server... (${attempt}/${max_attempts})"
  sleep 2
done

echo "  Server is up. Sending one chat completion request..."
echo ""

RESPONSE=$(curl -sf -X POST "${ENDPOINT}" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "",
    "messages": [{"role": "user", "content": "Say exactly: smoke test ok"}],
    "max_tokens": 32,
    "temperature": 0
  }')

if echo "${RESPONSE}" | grep -q '"choices"'; then
  echo "Response (choices):"
  echo "${RESPONSE}" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for c in d.get('choices', []):
    print('  ', c.get('message', {}).get('content', ''))
"
  echo ""
  echo "Smoke test PASSED: received valid completion."
  exit 0
else
  echo "Response: ${RESPONSE}"
  echo "Smoke test FAILED: no choices in response."
  exit 1
fi
