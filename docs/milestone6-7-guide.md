# Hướng dẫn triển khai Milestone 6 & 7

Tài liệu giải thích chi tiết và hướng dẫn triển khai **Milestone 6 (Autoscale: scale-to-zero)** và **Milestone 7 (Admission control + degradation ladder)**.

---

## Tổng quan

| Milestone | Mục tiêu | Output chính |
|-----------|----------|--------------|
| **M6** | Tự động start/stop worker theo nhu cầu (scale-to-zero) | Supervisor state machine, healthcheck, xử lý cold-start |
| **M7** | Tránh quá tải: từ chối khi queue đầy, giảm tải theo bậc (degradation) | 429 + Retry-After, thang degradation (max_tokens), log tier |

---

# MILESTONE 6 — Autoscale: start/stop by demand (scale-to-zero)

## 1. Mục tiêu và ý tưởng

### Mục tiêu (theo plan)

- **Supervisor state machine**: start worker khi `queue_depth > 0`, stop worker khi idle `idle_timeout` (mặc định 180s).
- **Healthcheck** (HTTP) để biết khi worker READY.
- **Cold-start**: request đến khi worker đang STARTING → giữ trong queue và đợi worker sẵn sàng (hoặc trả 503 nếu timeout).

### Tại sao scale-to-zero?

- Tiết kiệm tài nguyên GPU khi không có traffic: worker tắt → GPU rảnh.
- Khi có request, supervisor khởi động worker; request đầu tiên sau idle chịu **cold start** (vài giây đến vài chục giây tùy model).

### Tham khảo

- [Knative scale-to-zero](https://knative.dev/docs/serving/): mô hình scale về 0 khi không có traffic.

---

## 2. Kiến trúc M6

```
Client  →  Gateway  →  Supervisor (state machine)  →  Worker process (vLLM)
                         │
                         ├─ idle      : không process
                         ├─ starting  : đã spawn, đang chờ healthcheck
                         ├─ running   : healthcheck OK, nhận request
                         └─ stopping  : đang tắt process
                                    → idle (sau idle_timeout khi running)
```

- **Control plane**: Gateway + Supervisor (trong cùng process gateway khi `ENABLE_SUPERVISOR=1`).
- **Data plane**: Worker (vLLM) do supervisor spawn/kill.

---

## 3. Cấu trúc code đã triển khai

```
scripts/
├── worker_process.py   # Spawn/kill vLLM subprocess (cùng args với run_vllm_worker.sh)
├── supervisor.py       # State machine, healthcheck, idle timeout loop
├── policies.py        # M7: admission + degradation
└── gateway.py         # Tích hợp supervisor + cold-start + M7
```

### worker_process.py

- **WorkerProcess**: `start()`, `stop()`, `is_alive()`, `get_pid()`.
- Build lệnh vLLM từ env (`VLLM_MODEL`, `VLLM_PORT`, `VLLM_MAX_NUM_SEQS`, …) giống `run_vllm_worker.sh`.
- Dùng `vllm serve MODEL ...` (tìm `vllm` trong PATH hoặc `python -m vllm`).

### supervisor.py

- **WorkerState**: `idle` → `starting` → `running` → (idle timeout) → `stopping` → `idle`.
- **Supervisor**:
  - `start_if_needed()`: nếu idle thì chuyển starting và spawn worker.
  - `healthcheck()`: GET `{worker_url}/v1/models` để kiểm tra worker sống.
  - `run_loop()`: task nền — khi starting thì poll healthcheck; khi running thì kiểm tra idle timeout (mặc định 180s), nếu vượt thì stopping rồi idle.
  - `request_activity()`: gateway gọi mỗi khi có request để cập nhật thời điểm “có hoạt động” (tránh tắt khi vẫn còn traffic).

### Cold-start trong gateway

- Khi nhận request và supervisor bật:
  1. `request_activity()`; `start_if_needed()`.
  2. Chờ worker ready: poll `is_ready()` mỗi giây, tối đa 300s.
  3. Nếu timeout → trả **503** + header `Retry-After: 60`.
  4. Nếu ready → forward request như bình thường (có thể qua batching).

---

## 4. Cách chạy M6

### Chế độ không scale-to-zero (như cũ)

- Chạy vLLM thủ công, rồi chạy gateway. Supervisor không dùng.

```bash
./scripts/run_vllm_worker.sh
# Terminal khác:
./scripts/run_gateway.sh
```

### Chế độ scale-to-zero (M6)

- **Không** cần chạy vLLM trước. Chỉ cần chạy gateway với `ENABLE_SUPERVISOR=1`.

```bash
ENABLE_SUPERVISOR=1 ./scripts/run_gateway.sh
```

- Request đầu tiên: gateway start worker, đợi healthcheck OK (cold start), rồi xử lý.
- Sau khi không còn request trong **180 giây** (mặc định), supervisor tắt worker.
- Request tiếp theo sau đó lại trigger start → lại cold start.

### Tùy chỉnh

```bash
ENABLE_SUPERVISOR=1 IDLE_TIMEOUT_SEC=120 ./scripts/run_gateway.sh
```

- **IDLE_TIMEOUT_SEC**: số giây không có hoạt động thì tắt worker (mặc định 180).

### Kiểm tra

- Health gateway (có worker_state khi bật supervisor):

```bash
curl http://localhost:8001/health
# {"status":"ok","batch_window_ms":0,"worker_state":"running"}
```

- Metrics (queue, worker state, in-flight):

```bash
curl http://localhost:8001/metrics
```

---

## 5. Lưu ý M6

- **Cold start**: Request đầu tiên sau idle có thể mất vài giây đến vài chục giây; SLO nên hiểu là “p95 bỏ qua cold start” hoặc tách metric cold start (M8).
- **Single process**: Supervisor chạy trong process gateway; worker là subprocess. Một node, một worker phù hợp lab hiện tại.
- **Healthcheck**: Dùng `/v1/models` vì vLLM có sẵn endpoint này; nếu cần có thể đổi sang endpoint khác trong `supervisor.py`.

---

# MILESTONE 7 — Admission control + degradation ladder

## 1. Mục tiêu và ý tưởng

### Mục tiêu (theo plan)

- Nếu `queue_depth > Q_MAX` → trả **429** + header **Retry-After**.
- **Degradation ladder**: khi tải cao, giảm dần:
  - `max_new_tokens` (200 → 128 → 96 → 64),
  - (ở tầng worker: có thể giảm `max_model_len`, `max_num_seqs` — M7 triển khai bước giảm tại request: `max_tokens`).
- Log rõ **degradation tier** đang dùng để debug.

### Tại sao?

- **429**: Bảo vệ hệ thống khỏi quá tải; client retry sau.
- **Degradation**: Ưu tiên vẫn phục vụ nhưng giảm “chất lượng” (ít token hơn) thay vì từ chối hẳn.

---

## 2. Kiến trúc M7

- **Queue depth** = số request đang chờ trong batch queue + số request đang in-flight (đã gửi xuống worker chưa xong).
- **Admission**: `queue_depth > Q_MAX` → 429, không cho vào queue.
- **Degradation**: theo `queue_depth` chọn tier → sửa `max_tokens` trong body trước khi forward.

---

## 3. Code đã triển khai (policies.py + gateway)

### Admission (policies.check_admission)

- `check_admission(queue_depth, q_max)`:
  - `queue_depth <= Q_MAX` → admitted.
  - Ngược lại → `AdmissionResult(admitted=False, retry_after_sec=60)`.
- Gateway trả 429 với body `{"error": "overload", "reason": "..."}` và header `Retry-After: 60` (có thể cấu hình).

### Degradation ladder (policies.apply_degradation)

- **Tier 0**: queue_depth ≤ 32 → `max_tokens` giữ nguyên (tối đa 200).
- **Tier 1**: 33–64 → cap `max_tokens` = 128.
- **Tier 2**: 65–96 → cap 96.
- **Tier 3**: 97+ → cap 64.

- `apply_degradation(body, queue_depth)` trả `(body_đã_sửa, tier)`; khi có áp dụng thì log tier (ví dụ: `Degradation tier 1 active (queue_depth=50): max_new_tokens=128`).

### Gateway tích hợp M7

1. Tính `queue_depth = len(_pending) + _in_flight`.
2. Gọi `check_admission(queue_depth, Q_MAX)` → nếu không admitted thì return 429 ngay.
3. Gọi `apply_degradation(body, queue_depth)` → dùng body đã giảm tải để forward.

---

## 4. Cách chạy và tùy chỉnh M7

### Mặc định

- `Q_MAX=128` (env hoặc default trong code).
- Gateway đã bật admission và degradation.

```bash
./scripts/run_gateway.sh
# Hoặc qua vLLM:
./scripts/run_vllm_worker.sh
./scripts/run_gateway.sh
```

### Tùy chỉnh Q_MAX

```bash
Q_MAX=64 ./scripts/run_gateway.sh
```

- Queue depth > 64 → 429.

### Xem degradation trong log

- Khi queue sâu, log gateway sẽ có dòng kiểu:
  - `Degradation tier 1 active (queue_depth=50): max_new_tokens=128`

### Metrics

- `curl http://localhost:8001/metrics` có `gateway_queue_depth`, `gateway_in_flight`, `gateway_pending_batch`, (khi bật supervisor) `gateway_worker_state`.

---

## 5. Định nghĩa Q_MAX từ M4 (plan)

- Nên lấy từ kết quả M4: tại RPS mà p95 đạt ngưỡng SLO, queue depth lúc đó là tham chiếu.
- Đặt `Q_MAX` sao cho vượt quá độ sâu đó thì khả năng cao sẽ vi phạm SLO → từ chối (429) hợp lý.

---

## 6. Tóm tắt workflow M6 + M7

### M6

1. Bật supervisor: `ENABLE_SUPERVISOR=1 ./scripts/run_gateway.sh`.
2. Gửi request → gateway start worker nếu idle, đợi ready (cold start) rồi forward.
3. Sau 180s không request → supervisor tắt worker.
4. Kiểm tra `/health` (worker_state), `/metrics`.

### M7

1. Admission: `Q_MAX` (env, default 128); queue_depth > Q_MAX → 429 + Retry-After.
2. Degradation: theo queue_depth giảm `max_tokens` (200→128→96→64), log tier.
3. Tùy chỉnh: `Q_MAX=64` (hoặc giá trị phù hợp từ M4).

---

## 7. Tài liệu tham khảo

- [Knative scale-to-zero](https://knative.dev/docs/serving/)
- Plan: `docs/plan.md` — M6, M7
- vLLM tuning: giảm `max_num_seqs` / `max_num_batched_tokens` khi áp lực KV (worker profile, có thể mở rộng sau)
