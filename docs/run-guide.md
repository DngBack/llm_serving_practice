# Hướng dẫn chạy lab từ đầu đến cuối

Lab này **không dùng Kubernetes**. Auto-scale (scale-to-zero) được triển khai bằng **process start/stop** (supervisor spawn/kill vLLM), không phải K8s HPA/replicas.

Chạy theo đúng thứ tự: **Service → Management → Tests**.

---

## Tổng quan thứ tự chạy

| Bước | Thành phần | Mô tả |
|------|------------|-------|
| **1. Service** | vLLM Worker (data plane) | Engine inference, chạy trên GPU |
| **2. Management** | Gateway + Prometheus + Grafana | Control plane + observability |
| **3. Tests** | Smoke test, Load test | Kiểm tra hoạt động |

---

## Bước 1: Run Service (Data plane)

Chạy **vLLM worker** — engine inference.

```bash
cd /path/to/llm_serving_practice
./scripts/run_vllm_worker.sh
```

- Port: **8000**
- Đợi đến khi thấy log "Application startup complete" (vài chục giây đến vài phút lần đầu).
- **Giữ terminal này mở** — vLLM chạy foreground.

**Kiểm tra nhanh:**
```bash
curl -s http://localhost:8000/v1/models | head -20
```

---

## Bước 2: Run Management (Control plane + Observability)

Mở **2 terminal mới** (vLLM vẫn chạy ở terminal 1).

### 2a. Gateway (control plane)

```bash
./scripts/run_gateway.sh
```

- Port: **8001**
- Gateway nhận request, proxy sang vLLM, xử lý queue, admission, degradation.
- **Giữ terminal mở.**

**Tùy chọn scale-to-zero (M6):** Không cần chạy vLLM trước, gateway tự start/stop worker:
```bash
ENABLE_SUPERVISOR=1 ./scripts/run_gateway.sh
```

### 2b. Prometheus + Grafana (observability)

```bash
./scripts/run_monitoring.sh
```

- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin/admin)
- Scrape metrics từ vLLM (port 8000) và gateway (nếu có /metrics).

**Lưu ý:** Cần Docker. Trên Linux nếu `host.docker.internal` lỗi, sửa `infra/compose/prometheus.yml` (xem docs/milestone3-guide.md).

---

## Bước 3: Run Tests

Sau khi **Service** và **Management** đã chạy, mở terminal mới.

### 3a. Smoke test (1 request)

```bash
./scripts/smoke_test.sh
```

Gửi 1 request qua vLLM trực tiếp (port 8000). Nếu dùng gateway, sửa host trong script hoặc:

```bash
curl -X POST http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-3.5-turbo","messages":[{"role":"user","content":"Hi"}],"max_tokens":10,"temperature":0}'
```

### 3b. Load test (qua gateway)

```bash
./scripts/run_loadtest.sh http://localhost:8001
```

- 20 users, 10 phút
- Kết quả: RPS, p50/p95, error rate
- Report: `experiments/runs/locust_*_report.html`

### 3c. Các test khác

| Test | Lệnh |
|------|------|
| Admission (Q_MAX=10, 20 users) | `Q_MAX=10 ./scripts/run_gateway.sh` rồi `LOADTEST_USERS=20 LOADTEST_RUNTIME=1m ./scripts/run_loadtest.sh http://localhost:8001` |
| Scale-to-zero demo | `ENABLE_SUPERVISOR=1 ./scripts/run_gateway.sh` rồi `./scripts/run_scale_to_zero_demo.sh` |
| Batching A/B | `./scripts/run_batch_abtest.sh` |

---

## Sơ đồ thứ tự chạy

```
Terminal 1                    Terminal 2                    Terminal 3
─────────────                  ─────────────                 ─────────────
Bước 1: Service                Bước 2a: Gateway               Bước 2b: Monitoring
./run_vllm_worker.sh    →     ./run_gateway.sh         →     ./run_monitoring.sh
     (port 8000)                    (port 8001)                     (9090, 3000)
     │                                   │
     └───────────────┬───────────────────┘
                     │
                     ▼
              Terminal 4: Bước 3
              ./run_loadtest.sh http://localhost:8001
```

---

## Tóm tắt lệnh (copy-paste)

```bash
# Terminal 1 — Service
./scripts/run_vllm_worker.sh

# Terminal 2 — Gateway (sau khi vLLM ready)
./scripts/run_gateway.sh

# Terminal 3 — Monitoring (optional)
./scripts/run_monitoring.sh

# Terminal 4 — Tests (sau khi gateway ready)
./scripts/smoke_test.sh
./scripts/run_loadtest.sh http://localhost:8001
```

---

## Dừng các service

```bash
# vLLM, Gateway: Ctrl+C trong terminal tương ứng

# Prometheus + Grafana
cd infra/compose && docker compose down
```

---

## Đo và Auto-scale hoạt động thế nào?

### Đo (Metrics)

| Nguồn | Endpoint | Prometheus scrape |
|-------|----------|-------------------|
| vLLM | `:8000/metrics` | Có (job: vllm) |
| Gateway | `:8001/metrics` | Có (job: gateway) |

**Gateway metrics** (dùng cho scaling):
- `gateway_queue_depth` — tổng pending + in-flight (điều khiển admission 429, degradation)
- `gateway_worker_state` — 0=idle, 1=starting, 2=running, 3=stopping
- `gateway_in_flight` — request đang xử lý

**Grafana**: Xem queue depth, worker state theo thời gian → thấy khi nào hệ thống scale.

### Auto-scale (logic hiện tại)

| Quyết định | Điều kiện | Hành động |
|------------|-----------|-----------|
| **Start worker** | `queue_depth > 0` (có request) | Supervisor spawn vLLM |
| **Stop worker** | `idle_timeout` (180s) không có request | Supervisor kill vLLM |

- Logic chạy **trong gateway** (supervisor), không đọc từ Prometheus.
- Metrics được **expose** để Prometheus scrape → Grafana hiển thị → quan sát được quyết định scale.

### Giới hạn

- **Scale 0↔1**: Có (scale-to-zero).
- **Scale 1→N**: Không — lab single GPU, 1 worker. Muốn scale 1→N cần K8s HPA + nhiều replica/GPU.
