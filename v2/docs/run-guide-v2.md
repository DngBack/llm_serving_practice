# Hướng dẫn chạy Version 2 — Docker + Kubernetes

Version 2 chạy trên **Kubernetes** (Minikube) với **Docker** images. Auto-scale qua **HPA** (Horizontal Pod Autoscaler).

---

## So sánh V1 và V2

| | V1 (root) | V2 (v2/) |
|---|-----------|----------|
| **Chạy** | Process (run_vllm_worker.sh, run_gateway.sh) | Docker + K8s |
| **Scale** | Supervisor spawn/kill process | K8s HPA |
| **GPU** | Host trực tiếp | nvidia.com/gpu trong pod |

---

## Yêu cầu

- **Docker** — build images
- **Kubernetes** — Minikube (hoặc Kind, cloud cluster)
- **NVIDIA GPU** — driver trên host, [nvidia-device-plugin](https://github.com/NVIDIA/k8s-device-plugin) trong cluster
- **kubectl** — cấu hình trỏ tới cluster

---

## Bước 1: Chuẩn bị Minikube + GPU

```bash
# Cài Minikube (nếu chưa có)
# https://minikube.sigs.k8s.io/docs/start/

# Start Minikube
minikube start --driver=docker

# Bật NVIDIA device plugin (addon có sẵn trong Minikube)
minikube addons enable nvidia-device-plugin
```

**Lưu ý:** Nếu Minikube đã bật addon (thấy "Enabled addons: nvidia-device-plugin" khi start), bỏ qua bước `addons enable`. Xem [Minikube GPU](https://minikube.sigs.k8s.io/docs/handbook/gpu/).

---

## Bước 2: Build images

Build trong môi trường Docker của Minikube để cluster dùng được:

```bash
cd /path/to/llm_serving_practice

# Chuyển Docker sang Minikube
eval $(minikube docker-env)

# Build
./v2/scripts/build_images.sh
```

---

## Bước 3: Deploy lên K8s

```bash
./v2/scripts/deploy_k8s.sh
```

Chờ pods ready:

```bash
kubectl get pods -n llm-lab -w
```

Worker có thể mất vài phút (pull model lần đầu).

---

## Bước 4: Lấy URL Gateway

```bash
# Minikube
minikube ip
# Gateway: http://<minikube-ip>:30081

# Hoặc tunnel
minikube service gateway -n llm-lab --url
```

---

## Bước 5: Chạy test

```bash
# Smoke test
curl -X POST "http://$(minikube ip):30081/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-3.5-turbo","messages":[{"role":"user","content":"Hi"}],"max_tokens":10,"temperature":0}'

# Load test (qua gateway)
./v1/scripts/run_loadtest.sh "http://$(minikube ip):30081"
```

---

## Cấu trúc v2/

```
v2/
├── docker/
│   ├── worker/          # vLLM image (GPU)
│   │   ├── Dockerfile
│   │   └── entrypoint.sh
│   └── gateway/         # Gateway image
│       └── Dockerfile
├── k8s/
│   ├── namespace.yaml
│   ├── worker-deployment.yaml
│   ├── worker-service.yaml
│   ├── worker-hpa.yaml
│   ├── gateway-deployment.yaml
│   ├── gateway-service.yaml
│   └── gateway-hpa.yaml
├── scripts/
│   ├── build_images.sh
│   └── deploy_k8s.sh
└── docs/
    └── run-guide-v2.md
```

---

## Dừng và xóa

```bash
kubectl delete -f v2/k8s/
# Hoặc
kubectl delete namespace llm-lab
```
