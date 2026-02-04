# Load-test harness (Milestone 2)

Harness để load test server vLLM (OpenAI-compatible) với workload cố định **200 token vào / 200 token ra**, thu thập **RPS**, **p50/p95 latency**, **error rate** cho tối ưu hóa data-driven.

---

## Mục tiêu Milestone 2

- **Script load test:** tốc độ request tăng dần (ramp-up) rồi giữ ổn định (constant arrival rate), workload cố định 200/200.
- **Thu thập metrics:** RPS (requests/sec), p50/p95 latency (ms), error rate (%).

Các số liệu này dùng cho Milestone 4 (grid search) và so sánh với SLO (Milestone 0).

---

## Cài đặt

Cài Locust (Python):

```bash
pip install locust
# hoặc thêm vào requirements: locust>=2.0
```

Đảm bảo vLLM worker đang chạy (Milestone 1):

```bash
./scripts/run_vllm_worker.sh
```

---

## Chạy load test

### 1. Chế độ UI (tùy chỉnh số user, spawn rate trên web)

Từ **thư mục gốc repo**:

```bash
locust -f loadtest/locustfile.py --host=http://localhost:8000
```

Mở http://localhost:8089, nhập số users và spawn rate, bấm Start. Locust hiển thị RPS, latency percentiles, failure % theo thời gian thực.

### 2. Chế độ headless (không UI, chạy 10 phút rồi thoát)

Số user và spawn rate cố định (constant arrival rate sau khi ramp):

```bash
locust -f loadtest/locustfile.py --host=http://localhost:8000 \
  --headless -u 20 -r 2 --run-time 10m
```

- `-u 20`: 20 user ảo
- `-r 2`: spawn 2 user mỗi giây (ramp dần lên 20)
- `--run-time 10m`: chạy 10 phút (phù hợp “sustained run” trong plan)

### 3. Ramp-up rồi giữ constant (Load shape)

Dùng shape: tăng user từ `min` → `max` trong `ramp_sec` giây, sau đó giữ `max` user đến hết thời gian chạy:

```bash
USE_RAMP_SHAPE=1 locust -f loadtest/locustfile.py --host=http://localhost:8000 \
  --headless --run-time 10m
```

Biến môi trường (tùy chọn):

- `LOCUST_RAMP_SEC=60` — thời gian ramp (giây)
- `LOCUST_MIN_USERS=2` — số user lúc bắt đầu
- `LOCUST_MAX_USERS=20` — số user sau ramp
- `LOCUST_SPAWN_RATE=2` — tốc độ spawn user/giây

### 4. Script có sẵn (xuất CSV + HTML)

```bash
./scripts/run_loadtest.sh [BASE_URL]
# Ví dụ:
./scripts/run_loadtest.sh
./scripts/run_loadtest.sh http://localhost:8000
```

Script sẽ:

- Chạy Locust headless với `LOADTEST_USERS`, `LOADTEST_SPAWN_RATE`, `LOADTEST_RUNTIME` (mặc định 20, 2, 10m).
- Nếu set `USE_RAMP_SHAPE=1` thì dùng ramp shape thay vì `-u`/`-r`.
- Ghi CSV và báo cáo HTML vào `experiments/runs/` (hoặc `LOADTEST_OUT_DIR`).

Sau khi chạy, xem **RPS, p50/p95, error rate** trong output terminal và trong file:

- `experiments/runs/locust_<timestamp>_stats.csv` — số liệu tổng hợp (RPS, percentiles, failures).
- `experiments/runs/locust_<timestamp>_report.html` — báo cáo HTML.

---

## Workload cố định (200/200)

- **Prompt:** nội dung từ `configs/prompts/prompt_200.txt`. Để đạt ~200 token vào, có thể mở rộng nội dung file này (hoặc dùng prompt lặp trong scenario).
- **Output:** `max_tokens=200`, `temperature=0` (deterministic, dễ so sánh giữa các lần chạy).

Scenario nằm trong `loadtest/scenarios/fixed_200_200.py`; Locust gọi `POST /v1/chat/completions` với payload đó.

---

## Các metric cần quan tâm

| Metric        | Ý nghĩa |
|---------------|--------|
| **RPS**       | Số request/giây (throughput). |
| **p50 latency** | 50% request có thời gian phản hồi ≤ giá trị này (ms). |
| **p95 latency** | 95% request ≤ giá trị này; thường dùng cho SLO (vd. p95 ≤ 5s). |
| **Error rate** | Tỷ lệ request lỗi (%). Mục tiêu ví dụ ≤ 0.1%. |

Locust in sẵn các giá trị này; file CSV có thêm chi tiết theo từng endpoint.

---

## Cấu trúc thư mục

```
loadtest/
├── README.md           # File này
├── locustfile.py       # Định nghĩa user (Fixed200200User) và optional LoadTestShape
└── scenarios/
    ├── __init__.py
    └── fixed_200_200.py  # Load prompt, build payload 200/200
```

Script chạy từ repo root: `scripts/run_loadtest.sh`.

---

## Tài liệu tham khảo

- [Locust quickstart](https://docs.locust.io/)
- Plan: [docs/plan.md](../docs/plan.md) — Milestone 2, Milestone 0 (SLO, sustained run).
