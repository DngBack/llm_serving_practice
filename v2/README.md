# Version 2 — Docker + Kubernetes

Chạy lab trên **Kubernetes** (Minikube) với **Docker** images. Auto-scale qua **HPA**.

## Cấu trúc

```
v2/
├── docker/       # Dockerfile worker + gateway
├── k8s/          # K8s manifests (Deployment, Service, HPA)
├── scripts/      # build_images.sh, deploy_k8s.sh
└── docs/        # run-guide-v2.md
```

## Quick start

```bash
# 1. Minikube + GPU
minikube start --driver=docker
minikube addons enable nvidia-device-plugin   # bỏ qua nếu đã bật

# 2. Build (từ repo root)
eval $(minikube docker-env)
./v2/scripts/build_images.sh

# 3. Deploy
./v2/scripts/deploy_k8s.sh

# 4. Test
./v1/scripts/run_loadtest.sh "http://$(minikube ip):30081"
```

Xem **[docs/run-guide-v2.md](docs/run-guide-v2.md)** để biết chi tiết.
