# Hướng dẫn triển khai Milestone 4 & 5

Tài liệu này giải thích chi tiết và hướng dẫn triển khai **Milestone 4 (Throughput optimization)** và **Milestone 5 (Micro-batching at gateway)**.

---

## Tổng quan

| Milestone | Mục tiêu | Output chính |
|-----------|----------|--------------|
| **M4** | Grid search các tham số vLLM để tối đa hóa RPS trong SLO | Best config (max_num_seqs, max_num_batched_tokens) + bảng kết quả |
| **M5** | Thêm batching window tại gateway để tăng RPS khi có burst | Gateway với window 0/20/50ms + A/B test so sánh |

---

# MILESTONE 4 — Throughput Optimization (Grid Search)

## 1. Mục tiêu và ý tưởng

### Mục tiêu
- **Cố định** `max_model_len=512` (đã chọn từ M1 cho 4GB VRAM)
- **Quét lưới** hai tham số chính:
  - `max_num_seqs`: 64 → 128 → 192 → 256 (dừng khi OOM hoặc latency tăng vọt)
  - `max_num_batched_tokens`: 4096 → 8192 → 12288 → 16384
- **Ghi nhận** cấu hình tốt nhất theo tiêu chí M0: **max RPS trong SLO** (vd. p95 ≤ 5s, error ≤ 0.1%)

### Trade-off cần hiểu

| Tham số | Tăng lên | Hệ quả |
|---------|----------|--------|
| `max_num_seqs` | Nhiều sequence hơn mỗi batch | ↑ Throughput, nhưng ↑ KV cache → dễ OOM, có thể ↑ latency |
| `max_num_batched_tokens` | Nhiều token xử lý mỗi bước | ↑ TTFT (time-to-first-token), ↑ throughput; có thể ↑ ITL (inter-token latency) |

**Chunked prefill** (`--enable-chunked-prefill`): cho phép prefill chạy từng chunk, không chặn decode. Giúp cân bằng prefill và decode, cải thiện throughput và latency.

## 2. Cấu trúc triển khai

```
configs/model_profiles/
├── throughput.yaml      # max_num_seqs cao, max_num_batched_tokens cao
├── aggressive.yaml      # thử nghiệm mạnh hơn
└── safe.yaml            # bảo thủ, tránh OOM

scripts/
├── tune_grid.py         # chạy grid search, ghi kết quả JSON
├── run_vllm_worker.sh   # hỗ trợ env vars mới (đã có)
└── run_loadtest.sh      # dùng cho mỗi điểm trong grid

experiments/runs/
└── YYYY-MM-DD_runXX_<profile>.json   # kết quả từng run
```

## 3. Các bước triển khai M4

### Bước 1: Tạo model profiles

Tạo `configs/model_profiles/throughput.yaml`:

```yaml
# Profile: throughput — tối ưu RPS
max_model_len: 512
max_num_seqs: 128
max_num_batched_tokens: 8192
gpu_memory_utilization: 0.85
enable_chunked_prefill: true
```

Các profile khác (`aggressive`, `safe`) tương tự, chỉ khác giá trị.

### Bước 2: Cập nhật run_vllm_worker.sh

Thêm hỗ trợ env vars:
- `VLLM_MAX_NUM_BATCHED_TOKENS`
- `VLLM_ENABLE_CHUNKED_PREFILL`

### Bước 3: Script tune_grid.py

Logic:
1. Định nghĩa grid: `max_num_seqs` × `max_num_batched_tokens`
2. Với mỗi điểm:
   - Khởi động vLLM với cấu hình tương ứng (qua env hoặc CLI)
   - Chạy load test 10 phút (hoặc ngắn hơn để thử nhanh)
   - Parse Locust CSV → RPS, p50, p95, error rate
   - Nếu OOM hoặc error > ngưỡng → bỏ qua, ghi log
3. Ghi kết quả vào `experiments/runs/YYYY-MM-DD_grid_<timestamp>.json`
4. In ra best point theo SLO

### Bước 4: Chạy grid search

```bash
# Chạy load test 1 lần (vLLM đang chạy với config từ env)
VLLM_MAX_NUM_SEQS=128 VLLM_MAX_NUM_BATCHED_TOKENS=8192 ./scripts/run_vllm_worker.sh
# Terminal khác:
python scripts/tune_grid.py --single

# Chạy grid đầy đủ (spawn vLLM từng config, mất vài giờ)
python scripts/tune_grid.py

# Chạy nhanh (run 1 phút mỗi điểm, grid thu nhỏ)
QUICK=1 python scripts/tune_grid.py
```

### Bước 5: Đọc kết quả

- File JSON: `experiments/runs/YYYY-MM-DD_grid_*.json`
- Best config: in ra cuối script
- So sánh với SLO (p95 ≤ 5s, error ≤ 0.1%)

## 4. Lưu ý khi chạy M4

- **OOM**: Nếu OOM, giảm `max_num_seqs` hoặc `max_num_batched_tokens`, không tăng nữa
- **Latency blow-up**: Nếu p95 vượt SLO, coi điểm đó không hợp lệ
- **Nhiễu**: Chạy mỗi config 2–3 lần, lấy median RPS
- **Chunked prefill**: vLLM V1 bật mặc định khi có thể; vẫn nên set rõ `--enable-chunked-prefill` để đảm bảo

---

# MILESTONE 5 — Micro-batching at Gateway

## 1. Mục tiêu và ý tưởng

### Mục tiêu
- Thêm **batching window** (10–30 ms) tại gateway: thu thập request trong khoảng thời gian này trước khi gửi sang worker
- **A/B test**: window = 0 ms vs 20 ms vs 50 ms
- **Guardrail**: Nếu latency vượt SLO → giảm window

### Tại sao micro-batching?

- vLLM đã có **continuous batching** nội bộ
- Gateway batching thêm một lớp: gom nhiều request nhỏ thành batch lớn hơn trước khi gửi
- Hữu ích khi **traffic bursty**: nhiều request đến gần nhau trong vài ms
- Nếu load đều, single-client, có thể không thấy lợi rõ; cần đo để xác nhận

### Tham khảo
- [Triton dynamic batching](https://github.com/triton-inference-server/server/blob/main/docs/user_guide/model_configuration.md#dynamic-batcher): delay để tạo batch lớn hơn

## 2. Kiến trúc

```
Client (Locust)  →  Gateway (FastAPI + batching)  →  vLLM Worker
                         ↑
                    Batching window:
                    - Thu thập request trong 0/20/50 ms
                    - Gửi batch tới worker (OpenAI API)
```

## 3. Các bước triển khai M5

### Bước 1: Gateway với batching window

Đã triển khai `scripts/gateway.py` và `scripts/run_gateway.sh`. Gateway (FastAPI) có:
- Endpoint `POST /v1/chat/completions` proxy tới vLLM
- **Batching logic**:
  - Request đến → đưa vào queue
  - Mỗi `window_ms` ms (hoặc khi queue đủ lớn), gom batch và gửi tới vLLM
  - vLLM hỗ trợ batch qua API? → Cần kiểm tra: OpenAI API thường gửi từng request. **Cách đơn giản**: gateway giữ connection, gom N request, gửi song song (asyncio.gather) hoặc tuần tự nhưng gần nhau. Hoặc dùng **single request** nhưng delay để chờ thêm request rồi gửi cùng lúc (parallel).

**Lưu ý**: OpenAI/vLLM API nhận từng request. "Batching" ở gateway có nghĩa là:
- **Option A**: Delay để nhiều request đến → gửi gần như đồng thời → vLLM sẽ batch chúng (continuous batching)
- **Option B**: Gateway gom nhiều request, gửi 1 batch request (nếu API hỗ trợ) — vLLM OpenAI API không hỗ trợ batch request trực tiếp

→ **Option A** là cách thực tế: gateway chỉ cần **delay** (batching window) trước khi forward. Request đầu vào queue, đợi `window_ms`, rồi forward. Nhiều request cùng window sẽ được forward gần nhau → vLLM batch chúng.

### Bước 2: Cấu hình window

```bash
# Không batching (baseline)
./scripts/run_gateway.sh

# Batching 20ms
BATCH_WINDOW_MS=20 ./scripts/run_gateway.sh

# Batching 50ms
BATCH_WINDOW_MS=50 ./scripts/run_gateway.sh
```

- `BATCH_WINDOW_MS=0` → không delay, forward ngay (baseline)
- `BATCH_WINDOW_MS=20` → đợi 20ms
- `BATCH_WINDOW_MS=50` → đợi 50ms

### Bước 3: A/B test script

```bash
# Chạy A/B test tự động: window 0, 20, 50 ms
./scripts/run_batch_abtest.sh
```

Script chạy load test 3 lần (window=0, 20, 50), ghi RPS và p95 vào `experiments/runs/`, so sánh.

### Bước 4: Guardrail

Nếu p95 > SLO (vd. 5s) → log warning, gợi ý giảm window (vd. 50→20, 20→0).

## 4. Lưu ý khi chạy M5

- **vLLM batching đủ?**: Nếu load test single-client không cho thấy lợi rõ từ gateway batching, có thể giữ window nhỏ (0–20ms) và ghi nhận trong báo cáo
- **Latency vs throughput**: Window lớn → throughput có thể tăng nhưng latency tăng (request đợi trong queue)
- **SLO**: Luôn kiểm tra p95 không vượt SLO

---

# Tóm tắt workflow

## M4
1. Tạo `configs/model_profiles/*.yaml`
2. Cập nhật `run_vllm_worker.sh` với env mới
3. Implement `scripts/tune_grid.py`
4. Chạy grid, phân tích JSON, chọn best config

## M5
1. Implement gateway với batching window (delay queue)
2. Chạy A/B test: window 0 vs 20 vs 50 ms
3. So sánh RPS, p95; thêm guardrail nếu vượt SLO

---

# Tài liệu tham khảo

- [vLLM Optimization](https://docs.vllm.ai/en/stable/configuration/optimization.html)
- [Triton Dynamic Batcher](https://github.com/triton-inference-server/server/blob/main/docs/user_guide/model_configuration.md#dynamic-batcher)
- Plan: `docs/plan.md` — M4, M5, M0 (SLO)
