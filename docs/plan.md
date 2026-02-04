# rtx3050-llm-throughput-lab — Plan & Milestones

This document defines the **milestone to-do list**, **repository structure**, **conventions**, and a **critical review** so the project stays focused and implementable on a single RTX 3050 4GB GPU.

---

## 1. Milestones (To-Do + Documentation)

Each milestone has a clear output. Documentation links support learning and tuning.

---

### Milestone 0 — Define the problem and winning criteria

**To-do**

- [ ] **Choose SLO:** e.g. p95 ≤ 5s, error rate ≤ 0.1%
- [ ] **Lock standard workload:** 200 in / 200 out, `temperature=0`
- [ ] **Lock measurement:** sustained RPS over a **10-minute** run

**Documentation**

- vLLM optimization mindset (KV cache, main knobs and their impact)

---

### Milestone 1 — Baseline serving (no autoscale)

**To-do**

- [x] Run **vLLM serve** with a ~0.5–0.6B model
- [x] Set `--max-model-len 512` for 4GB
- [x] Use `--gpu-memory-utilization 0.9` (default) to maximize KV cache usage
- [x] Run one request end-to-end (functional smoke test)

**Documentation**

- [vLLM serve CLI args](vllm-serve-args.md): `max-model-len`, `gpu-memory-utilization`, etc.

---

### Milestone 2 — Load-testing harness (data-driven optimization)

**To-do**

- [ ] Implement load-test script:
  - Constant arrival rate (ramp up gradually)
  - Fixed prompt/output (200/200)
- [ ] Collect metrics: **RPS**, **p50/p95 latency**, **error rate**

**Documentation (pick one)**

- [Locust quickstart](https://docs.locust.io/) (Python, easy to model user flow)
- [k6 getting started](https://k6.io/docs/getting-started/) (JS, CI-friendly)

---

### Milestone 3 — Observability (find bottlenecks)

**To-do**

- [ ] Expose **metrics endpoint** from gateway/supervisor (Prometheus format)
- [ ] Set up **Prometheus scrape** + **Grafana** dashboard
- [ ] Track at least:
  - queue depth, queue wait time
  - request latency histogram
  - in-flight requests
  - worker state (running/stopped)
  - error counters

**Documentation**

- [Prometheus getting started](https://prometheus.io/docs/introduction/first_steps/)
- [Prometheus client libraries](https://prometheus.io/docs/instrumenting/clientlibs/) (e.g. Python client)
- [Grafana Prometheus data source](https://grafana.com/docs/grafana/latest/datasources/prometheus/)

---

### Milestone 4 — Throughput optimization (disciplined grid search)

**To-do**

- [ ] Fix `max_model_len=512`
- [ ] Sweep:
  - `max_num_seqs`: 64 → 128 → 192 → 256 (stop when OOM or latency blows up)
  - `max_num_batched_tokens`: 4096 → 8192 → 12288 → 16384
- [ ] Record **best point** against Milestone 0 criteria (max RPS under SLO)

**Documentation**

- vLLM optimization guide (KV cache vs `max_num_seqs` / `max_num_batched_tokens`)
- `--enable-chunked-prefill` (prevents prefill from blocking decode under load)
- Document trade-off: throughput vs latency for batching parameters

---

### Milestone 5 — Micro-batching at gateway (higher RPS on bursts)

**To-do**

- [ ] Add **batching window** (10–30 ms) before sending to worker
- [ ] A/B test: window = 0 ms vs 20 ms vs 50 ms
- [ ] Guardrail: if latency exceeds SLO, reduce window

**Documentation**

- [Triton delayed batching](https://github.com/triton-inference-server/server/blob/main/docs/user_guide/model_configuration.md#dynamic-batcher) (delay to form larger batches)
- [Triton dynamic batching](https://github.com/triton-inference-server/server/blob/main/docs/user_guide/model_configuration.md#dynamic-batcher) (throughput via batching)

---

### Milestone 6 — Autoscale: start/stop by demand (scale-to-zero)

**To-do**

- [ ] Implement **supervisor state machine**:
  - start worker when `queue_depth > 0`
  - stop worker when idle for `idle_timeout=180s`
- [ ] **Healthcheck** worker (HTTP) to know when READY
- [ ] **Cold-start handling:** requests while STARTING → keep in queue and return "processing/queued" or hold connection (your choice)

**Documentation**

- [Knative scale-to-zero](https://knative.dev/docs/serving/) (reference pattern)

---

### Milestone 7 — Admission control + degradation ladder (avoid overload)

**To-do**

- [ ] If `queue_depth > Q_MAX` → return **429** + `Retry-After`
- [ ] **Degradation ladder:**
  - reduce `max_new_tokens` (200 → 128)
  - reduce `max_model_len` (512 → 448)
  - reduce `max_num_seqs`
- [ ] Log clearly **which degradation tier** is active for debugging

**Documentation**

- vLLM tuning: reducing `max_num_seqs` / `max_num_batched_tokens` under KV pressure

---

### Milestone 8 — Results report (showcase)

**To-do**

- [ ] One **results table:** config → max RPS @ p95 latency
- [ ] One **plot:** RPS vs p95 latency
- [ ] **Demo clip:** idle → worker stops → send load → worker starts automatically
- [ ] Separate description of **control plane** vs **data plane**

---

## 2. Architecture: control vs data plane

| Plane        | Components                                      | Role |
|-------------|--------------------------------------------------|------|
| **Control** | Gateway, Supervisor (start/stop worker, queue, admission) | Policy, scaling, queue, limits |
| **Data**    | Worker (vLLM) + config profiles                 | GPU inference only |

This keeps policy and scaling logic out of the inference path and makes tuning and debugging clearer.

---

## 3. Proposed repository structure

Keep **source code** separate from **config**, **infra**, and **experiments**.

```
rtx3050-llm-throughput-lab/
├── README.md
├── pyproject.toml
├── .gitignore
├── .env.example
│
├── src/
│   └── rtx3050_llm_lab/
│       ├── __init__.py
│       ├── gateway/                 # FastAPI entry + routes
│       │   ├── app.py               # create_app(), lifespan
│       │   ├── routes.py            # /generate, /health, /metrics
│       │   ├── schemas.py           # request/response models
│       │   └── settings.py          # env config
│       ├── supervisor/              # scale-to-zero controller
│       │   ├── supervisor.py        # state machine
│       │   ├── worker_process.py    # spawn/kill vLLM
│       │   └── policies.py          # admission + degrade rules
│       ├── queue/                   # queue abstraction (Redis optional)
│       │   ├── interface.py
│       │   ├── redis_queue.py
│       │   └── memory_queue.py
│       ├── client/                  # internal client to vLLM worker
│       │   └── vllm_openai_client.py  # OpenAI-compatible API
│       └── observability/
│           ├── metrics.py
│           └── logging.py
│
├── configs/
│   ├── model_profiles/              # "throughput", "aggressive", …
│   │   ├── throughput.yaml
│   │   └── aggressive.yaml
│   └── prompts/                    # fixed prompts for benchmarking
│       ├── prompt_200.txt
│       └── system.txt
│
├── infra/
│   ├── docker/
│   │   ├── worker/                  # vLLM container
│   │   │   ├── Dockerfile           # (optional) if customized
│   │   │   └── run_worker.sh
│   │   └── gateway/                 # (optional) if containerized
│   │       └── Dockerfile
│   ├── compose/
│   │   ├── docker-compose.yml       # gateway + redis + monitoring
│   │   ├── docker-compose.gpu.yml   # vLLM worker (GPU) profile
│   │   └── prometheus.yml
│   └── grafana/
│       ├── provisioning/            # datasources + dashboards
│       └── dashboards/
│
├── loadtest/
│   ├── locustfile.py                # or k6/
│   ├── scenarios/
│   │   └── fixed_200_200.py
│   └── README.md
│
├── experiments/
│   ├── runs/                       # tuning run outputs
│   │   ├── 2026-02-04_run01.json
│   │   └── ...
│   └── notebooks/                  # analysis (optional)
│
├── scripts/
│   ├── bench.py                    # run benchmark + log results
│   ├── tune_grid.py                # sweep max_num_seqs / batched_tokens
│   └── smoke_test.sh
│
├── docs/
│   └── plan.md                     # this file
│
└── tests/
    ├── test_gateway.py
    └── test_policies.py
```

**Why this is clean**

- **`src/` layout:** avoids importing from repo root, clearer tests and packaging.
- **`configs/`:** tuning and profiles live outside code.
- **`infra/`:** all Docker/Compose/monitoring in one place.
- **`experiments/`:** benchmark outputs stay out of the main codebase.
- **`scripts/`:** one-off tooling for benchmarks and tuning.

---

## 4. Key decisions (for long-term clarity)

### API: OpenAI-compatible between gateway and worker

vLLM runs an OpenAI-compatible server. The gateway calls `POST /v1/chat/completions` (or `/v1/completions`). This keeps the gateway engine-agnostic and simplifies client code.

### Monitoring in infra

Prometheus and Grafana live under `infra/compose` and `infra/grafana` (provisioning + dashboards). No monitoring config mixed into application source.

### Gateway structure (FastAPI)

Use multiple modules (e.g. `app.py`, `routes.py`, `schemas.py`, `settings.py`) as in [FastAPI’s “bigger applications”](https://fastapi.tiangolo.com/tutorial/bigger-applications/) so the gateway can grow without becoming a single huge file.

### Compose split

- **`docker-compose.yml`:** gateway, Redis, Prometheus, Grafana (no GPU).
- **`docker-compose.gpu.yml`:** vLLM worker (GPU). Use when you need the worker; vLLM’s Docker docs fit this workflow.

---

## 5. Naming conventions

| Thing              | Convention |
|--------------------|------------|
| Python package     | `rtx3050_llm_lab` |
| Compose services   | `gateway`, `supervisor`, `redis`, `worker`, `prometheus`, `grafana` |
| Model profiles     | `throughput`, `aggressive`, `safe` |
| Experiment output  | `YYYY-MM-DD_runXX_<profile>.json` |

---

## 6. Critical review (phản biện)

### What works well

1. **Milestone order** — 0 (SLO) → 1 (baseline) → 2 (harness) → 3 (observability) → 4 (tuning) gives a clear path: define success, get something running, measure, then optimize.
2. **Fixed workload (200/200)** — Makes benchmarks comparable and focuses tuning on throughput/latency, not prompt length variance.
3. **Control vs data plane** — Keeps scaling and policy in the supervisor/gateway and leaves the worker as a “dumb” inference endpoint, which is easy to reason about and tune.
4. **`src/` + configs + infra + experiments** — Good separation for a small team and for future packaging or reuse.
5. **OpenAI-compatible worker** — Standard interface, easy to swap vLLM for another engine later.
6. **Degradation ladder (M7)** — Prefer degrading (shorter output, smaller context) over hard 429 when possible; 429 as last resort is the right idea.

### What to watch or simplify

1. **Redis in M6** — For a single-node, single-worker lab, an **in-memory queue** is enough at first. Add Redis when you need persistence or multi-process gateway. Implementing `memory_queue` first keeps M1–M5 simpler.
2. **Scale-to-zero complexity (M6)** — Cold start on a 0.5B model is a few seconds; 180s idle timeout is reasonable. Document “first request after idle pays cold start” so SLO is interpreted correctly (e.g. “p95 excluding cold start” or separate cold-start metric).
3. **Micro-batching (M5) vs vLLM’s own batching** — vLLM already does continuous batching. Gateway batching adds another layer: you form a batch over 10–30 ms then send. This can help if the gateway sees many tiny bursts. Validate with the M2 harness; if single-client load doesn’t show clear gain, you can keep the window small or 0 and document that vLLM batching was sufficient.
4. **Observability (M3) before or after M4** — Having metrics before M4 is ideal so you can see OOM vs latency during the grid search. If time is short, a minimal metrics endpoint (e.g. request count, latency histogram) plus Prometheus scrape is enough; full Grafana dashboards can follow.
5. **Admission Q_MAX (M7)** — Define `Q_MAX` from M4 results: e.g. “at RPS X we see p95 at SLO limit,” so queue depth at that load becomes a reference. Tune Q_MAX so that beyond it you’re likely to breach SLO, then 429.

### Risks and mitigations

| Risk | Mitigation |
|------|-------------|
| vLLM version/API drift | Pin vLLM version in `pyproject.toml` / Docker; check release notes when upgrading. |
| 4GB OOM during grid search | Start with conservative `max_num_seqs` (e.g. 64) and step up; run sweep in a script that catches OOM and records last good config. |
| Supervisor/worker race on startup | Use healthcheck (HTTP) and only mark worker READY when vLLM responds; gateway queues or retries until READY. |
| “Best point” in M4 is noisy | Run each config 2–3 times (e.g. 10 min each), take median RPS; document run length and SLO in the results table. |

### Optional simplifications (if scope creeps)

- **Grafana:** Start with Prometheus + raw queries or a single static dashboard; add full Grafana provisioning later.
- **Redis:** Omit until you need multi-process or persistence; use `memory_queue` only.
- **Degradation ladder:** Implement one step first (e.g. reduce `max_new_tokens`), then add more steps if needed.
- **Demo clip (M8):** A short script (idle → wait → send requests → show worker up) can replace a video for a doc-only report.

---

## 7. Summary

The **milestones and architecture are sound** for a single-GPU, throughput-focused lab: clear SLO, baseline → harness → observability → tuning → batching → scale-to-zero → admission/degradation → report. The proposed **repo layout and conventions** keep code, config, infra, and experiments separate and make the project easy to extend and to explain.

Main adjustments to keep in mind: start with **memory queue** and add Redis only when needed; validate **gateway micro-batching** with data before investing in it; define **Q_MAX** from M4 data; and document **cold-start** and **measurement methodology** so the M8 report and SLO are interpretable.

Use this document as the single source of truth for the plan; update it as you complete milestones or change decisions.
