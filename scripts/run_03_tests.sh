#!/usr/bin/env bash
# Bước 3: Run Tests
# Chạy smoke test + load test.
#
# Prerequisites: vLLM (Bước 1) và Gateway (Bước 2) đang chạy.
#
# Usage: ./scripts/run_03_tests.sh [BASE_URL]
#        ./scripts/run_03_tests.sh http://localhost:8001
#
# Nếu không truyền BASE_URL, mặc định dùng gateway (8001).

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

BASE_URL="${1:-http://localhost:8001}"

echo "=== Bước 3: Run Tests ==="
echo "  Target: $BASE_URL"
echo ""

# Kiểm tra gateway/vLLM có chạy không
if ! curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/v1/models" 2>/dev/null | grep -q 200; then
  if [[ "$BASE_URL" == *":8001"* ]]; then
    echo "ERROR: Gateway không chạy tại $BASE_URL"
    echo "Chạy Bước 2 trước: ./scripts/run_02_management.sh"
  else
    echo "ERROR: Service không phản hồi tại $BASE_URL"
    echo "Chạy Bước 1 và 2 trước."
  fi
  exit 1
fi

echo "  3a. Smoke test..."
./scripts/smoke_test.sh "$BASE_URL"

echo ""
echo "  3b. Load test (20 users, 10 phút)..."
LOADTEST_USERS=20 LOADTEST_RUNTIME=10m ./scripts/run_loadtest.sh "$BASE_URL"

echo ""
echo "=== Tests xong ==="
echo "  Report: experiments/runs/locust_*_report.html"
