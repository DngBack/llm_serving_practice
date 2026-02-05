#!/usr/bin/env bash
# Bước 2: Run Management (Control plane + Observability)
# Chạy Gateway + Prometheus + Grafana.
#
# Prerequisites: vLLM đang chạy (Bước 1) — trừ khi dùng ENABLE_SUPERVISOR=1
#
# Chạy trong Terminal 2. Giữ terminal mở (gateway chạy foreground).
# Sau khi ready, mở Terminal 3 và chạy tests (Bước 3).
#
# Usage: ./scripts/run_02_management.sh
#        ENABLE_SUPERVISOR=1 ./scripts/run_02_management.sh  # scale-to-zero, không cần vLLM trước

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "=== Bước 2: Run Management ==="
echo ""

# 2a. Prometheus + Grafana (nếu có Docker)
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  echo "  Starting Prometheus + Grafana..."
  ./scripts/run_monitoring.sh
  echo ""
else
  echo "  (Docker không có hoặc không chạy — bỏ qua Prometheus/Grafana)"
  echo ""
fi

# 2b. Gateway
echo "  Starting Gateway (port 8001)..."
echo "  Sau khi ready, chạy tests: ./scripts/run_03_tests.sh"
echo ""

exec ./scripts/run_gateway.sh
