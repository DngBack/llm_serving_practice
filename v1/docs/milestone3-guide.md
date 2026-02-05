# Milestone 3 — Observability: Hướng dẫn triển khai chi tiết

## 1. Tổng quan Milestone 3

**Mục tiêu:** Xây dựng hệ thống quan sát (observability) để tìm bottleneck khi tối ưu throughput. Khi có metrics và dashboard, bạn có thể:

- Theo dõi **queue depth**, **queue wait time** → biết khi nào request bị chờ
- Xem **request latency histogram** (p50, p95) → đánh giá SLO
- Theo dõi **in-flight requests** → biết mức độ tải
- Kiểm tra **worker state** (running/stopped) → biết worker có sẵn sàng không
- Đếm **error** → phát hiện lỗi sớm

---

## 2. Kiến trúc Observability

```
┌─────────────┐     scrape      ┌──────────────┐     query      ┌─────────┐
│   vLLM      │ ◄────────────── │  Prometheus  │ ◄───────────── │ Grafana │
│  :8000      │   /metrics      │   :9090      │                │  :3000  │
│  (worker)   │                 │              │                │         │
└─────────────┘                 └──────────────┘                └─────────┘
```

- **vLLM** đã có sẵn endpoint `/metrics` (Prometheus format) mặc định.
- **Prometheus** scrape metrics định kỳ (mặc định 15s).
- **Grafana** kết nối Prometheus làm datasource và hiển thị dashboard.

---

## 3. Các metrics cần theo dõi (theo plan)

| Metric | Mô tả | vLLM metric tương ứng |
|--------|-------|------------------------|
| **Queue depth** | Số request đang chờ trong queue | `vllm:num_requests_waiting` |
| **Queue wait time** | Thời gian chờ trong queue | `vllm:request_queue_time_seconds` |
| **Request latency** | Latency end-to-end (histogram) | `vllm:e2e_request_latency_seconds` |
| **In-flight requests** | Số request đang xử lý | `vllm:num_requests_running` |
| **Worker state** | Worker running/stopped | Prometheus `up` (target up/down) |
| **Error counters** | Số request lỗi | `vllm:request_failure_total`, `vllm:request_success_total` |

vLLM đã expose tất cả các metrics này. Khi có **gateway** (M5/M6), bạn sẽ thêm metrics ở tầng gateway (queue depth tại gateway, latency qua gateway, v.v.).

---

## 4. Các bước triển khai

### Bước 1: Chuẩn bị môi trường

```bash
# Đảm bảo đã cài Docker và Docker Compose
docker --version
docker compose version
```

### Bước 2: Khởi động vLLM worker

```bash
./scripts/run_vllm_worker.sh
```

Kiểm tra metrics có sẵn:

```bash
curl http://localhost:8000/metrics
```

Bạn sẽ thấy output dạng Prometheus (ví dụ: `vllm:e2e_request_latency_seconds_bucket`, `vllm:num_requests_running`, ...).

### Bước 3: Cấu hình Prometheus

File `infra/compose/prometheus.yml` đã được tạo sẵn. Docker Compose dùng `extra_hosts: host.docker.internal:host-gateway` để container có thể truy cập vLLM trên host.

**Nếu scrape lỗi trên Linux:** Sửa `prometheus.yml`, thay `host.docker.internal:8000` bằng:
- `172.17.0.1:8000` (Docker bridge default)
- Hoặc IP máy host của bạn (vd: `192.168.1.100:8000`)

### Bước 4: Chạy Prometheus + Grafana bằng Docker Compose

```bash
./scripts/run_monitoring.sh
# hoặc
cd infra/compose && docker compose up -d
```

Truy cập:

- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (đăng nhập: admin/admin)

### Bước 5: Thêm Prometheus làm datasource trong Grafana

1. Vào **Connections** → **Data sources** → **Add data source**
2. Chọn **Prometheus**
3. URL: `http://prometheus:9090` (tên service trong Docker network)
4. **Save & Test**

### Bước 6: Import dashboard vLLM

vLLM cung cấp dashboard mẫu. Có thể:

- Import từ [vLLM examples](https://github.com/vllm-project/vllm/blob/main/examples/online_serving/prometheus_grafana/grafana.json)
- Hoặc dùng dashboard có sẵn trong `infra/grafana/dashboards/`

---

## 5. Cấu trúc thư mục (sau khi triển khai)

```
infra/
├── compose/
│   ├── docker-compose.yml    # Prometheus + Grafana
│   └── prometheus.yml       # Cấu hình scrape
└── grafana/
    ├── provisioning/        # Auto-provision datasources (optional)
    └── dashboards/          # Dashboard JSON
```

---

## 6. Các truy vấn Prometheus hữu ích

| Mục đích | Query |
|----------|-------|
| p95 latency (s) | `histogram_quantile(0.95, sum(rate(vllm:e2e_request_latency_seconds_bucket[5m])) by (le))` |
| RPS (requests/sec) | `rate(vllm:e2e_request_latency_seconds_count[1m])` |
| In-flight | `vllm:num_requests_running` |
| Queue depth | `vllm:num_requests_waiting` |
| Error rate | `rate(vllm:request_failure_total[5m])` |

---

## 7. Khi có Gateway (M5/M6)

Khi triển khai gateway, bạn sẽ thêm:

- **Gateway metrics** (Prometheus Python client):
  - `gateway_requests_total` (counter)
  - `gateway_request_latency_seconds` (histogram)
  - `gateway_queue_depth` (gauge)
  - `gateway_queue_wait_seconds` (histogram)
  - `gateway_errors_total` (counter)
  - `gateway_worker_up` (gauge: 1 = ready, 0 = not ready)

Prometheus sẽ scrape thêm target `gateway:8080/metrics`. Dashboard Grafana có thể có 2 tab: "Worker (vLLM)" và "Gateway".

---

## 8. Tóm tắt checklist M3

- [ ] Prometheus scrape vLLM `/metrics`
- [ ] Grafana kết nối Prometheus
- [ ] Dashboard hiển thị: queue depth, queue wait, latency, in-flight, worker state, errors
- [ ] Chạy load test và xác nhận metrics cập nhật đúng

---

## 9. Tài liệu tham khảo

- [Prometheus getting started](https://prometheus.io/docs/introduction/first_steps/)
- [Prometheus Python client](https://github.com/prometheus/client_python)
- [Grafana Prometheus datasource](https://grafana.com/docs/grafana/latest/datasources/prometheus/)
- [vLLM Prometheus & Grafana](https://docs.vllm.ai/en/stable/getting_started/examples/prometheus_grafana.html)
- [vLLM Metrics Design](https://docs.vllm.ai/en/latest/design/metrics.html)
