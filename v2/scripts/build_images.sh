#!/usr/bin/env bash
# v2: Build Docker images for worker and gateway.
# Run from repo root. For Minikube: eval $(minikube docker-env) first.
#
# Usage:
#   ./v2/scripts/build_images.sh
#   eval $(minikube docker-env) && ./v2/scripts/build_images.sh  # for Minikube

set -e

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

echo "Building v2 images (context: $REPO_ROOT)"
echo ""

echo "  Building llm-worker:latest..."
docker build -f v2/docker/worker/Dockerfile -t llm-worker:latest .
echo "  Done."
echo ""

echo "  Building llm-gateway:latest..."
docker build -f v2/docker/gateway/Dockerfile -t llm-gateway:latest .
echo "  Done."
echo ""

echo "Images built: llm-worker:latest, llm-gateway:latest"
echo "For Minikube: run 'eval \$(minikube docker-env)' before this script."
