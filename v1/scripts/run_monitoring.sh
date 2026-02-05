#!/usr/bin/env bash
# Milestone 3: Start Prometheus + Grafana for observability.
#
# Prerequisites:
#   - vLLM worker running on host:8000 (./scripts/run_vllm_worker.sh)
#   - Docker and Docker Compose
#
# Usage:
#   ./scripts/run_monitoring.sh
#
# Access:
#   Prometheus: http://localhost:9090
#   Grafana:    http://localhost:3000 (admin/admin)
#   vLLM metrics: http://localhost:8000/metrics

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT/infra/compose"

echo "Starting Prometheus + Grafana (Milestone 3)"
echo "  Prometheus: http://localhost:9090"
echo "  Grafana:    http://localhost:3000"
echo ""
echo "Ensure vLLM is running: curl -s http://localhost:8000/metrics | head -5"
echo ""

docker compose up -d

echo ""
echo "Done. Open Grafana at http://localhost:3000 and import dashboard from"
echo "  Dashboards -> vLLM Lab — M3 Observability"
echo ""
echo "To stop: cd infra/compose && docker compose down"
