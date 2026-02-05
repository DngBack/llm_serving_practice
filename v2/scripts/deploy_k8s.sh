#!/usr/bin/env bash
# v2: Deploy to Kubernetes (namespace, worker, gateway, HPA).
#
# Prerequisites:
#   - kubectl configured (minikube, kind, or cloud cluster)
#   - Images built: llm-worker:latest, llm-gateway:latest
#   - For Minikube: images built with eval $(minikube docker-env)
#
# Usage:
#   ./v2/scripts/deploy_k8s.sh

set -e

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
K8S_DIR="$REPO_ROOT/v2/k8s"

echo "Deploying v2 to Kubernetes..."
echo "  Manifests: $K8S_DIR"
echo ""

kubectl apply -f "$K8S_DIR/namespace.yaml"
kubectl apply -f "$K8S_DIR/worker-deployment.yaml"
kubectl apply -f "$K8S_DIR/worker-service.yaml"
kubectl apply -f "$K8S_DIR/worker-hpa.yaml"
kubectl apply -f "$K8S_DIR/gateway-deployment.yaml"
kubectl apply -f "$K8S_DIR/gateway-service.yaml"
kubectl apply -f "$K8S_DIR/gateway-hpa.yaml"

echo ""
echo "Done. Wait for pods: kubectl get pods -n llm-lab -w"
echo "Gateway NodePort: 30081 — http://\$(minikube ip):30081 (if using Minikube)"
