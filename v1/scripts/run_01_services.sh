#!/usr/bin/env bash
# Bước 1: Run Service (Data plane)
# Chạy vLLM worker — engine inference trên GPU.
#
# Chạy trong Terminal 1. Giữ terminal mở.
# Sau khi thấy "Application startup complete", chuyển sang Bước 2.
#
# Usage: ./scripts/run_01_services.sh

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "=== Bước 1: Run Service (Data plane) ==="
echo "  vLLM Worker — port 8000"
echo ""
echo "  Sau khi ready, mở Terminal 2 và chạy: ./scripts/run_02_management.sh"
echo ""

exec ./scripts/run_vllm_worker.sh
