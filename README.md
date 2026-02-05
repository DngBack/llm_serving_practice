# llm-throughput-lab

A hands-on pet project to learn LLM serving design by building a small LLMOps stack that **maximizes throughput (requests/sec)** on a single GPU, using a ~0.6B model and a fixed workload: **200 input tokens + 200 output tokens**.

---

## Motivation

When GPU memory is small (4GB) and traffic is bursty, the hard problems are:

- **Keeping GPU utilization high** without blowing up latency.
- **Controlling KV-cache growth** by constraining context and concurrency.
- **Handling bursts safely** via queuing, micro-batching, and admission control.
- **Scale-to-zero:** automatically stop the model worker when idle, and restart it on demand.

This repo is a practical learning exercise focused on measurable performance, not a full production platform.

---

## Goals

### Primary goal

Maximize **sustained throughput (RPS)** for the fixed workload (200-in / 200-out) while meeting a defined SLO:

- Example SLO: **p95 latency ≤ 5s**, **error rate ≤ 0.1%** (tunable).

### Secondary goals

- Implement **scale-to-zero** (auto stop/start the model worker) based on request demand.
- Provide a **repeatable benchmark harness** and tuning playbook.
- Build an **observable system** (metrics + dashboards) to support engineering-style iteration.

### Non-goals

- Multi-GPU scheduling.
- Training or fine-tuning.
- Complex auth/billing/multi-tenant isolation.
- “Best model quality” tuning (focus is on throughput and stability).

---

## System Overview

### Components

| Component | Role |
|-----------|------|
| **Gateway API** (always-on) | Receives requests, validates payloads, implements rate limiting and admission control. |
| **Queue** | Buffers bursts and allows controlled batching. |
| **Supervisor** (control plane) | Starts/stops the model worker (scale-to-zero) and enforces policies. |
| **Model Worker** (data plane) | Runs an inference engine (e.g. **vLLM** server) with continuous batching knobs. |

### Model worker knobs (vLLM-style)

- `--max-model-len` — Controls model context length (prompt + output).
- `--gpu-memory-utilization` — Caps fraction of GPU memory used (default 0.9).
- `--max-num-seqs` and `--max-num-batched-tokens` — Control concurrency and token budget per scheduling step.

### Why micro-batching?

Micro-batching increases throughput by combining requests into batches, similar to dynamic batching patterns used in NVIDIA Triton Inference Server.

### Scale-to-zero concept

This project implements **scale-to-zero** locally (process start/stop). For reference, [Knative Serving](https://knative.dev/docs/serving/) describes scale-to-zero as scaling replicas down to zero when no traffic exists.

---

## Default Workload

- **Prompt length:** ~200 tokens  
- **Generation length:** ~200 tokens  
- **Sampling:** Deterministic for stable benchmarks (e.g. `temperature=0`)

---

## Suggested Baseline Model

A small instruct model around **0.5–0.6B parameters**, e.g. **Qwen2.5-0.5B-Instruct**.

The project is model-agnostic; you can swap models as long as the server supports them.

---

## Key Performance Levers

With 4GB VRAM, throughput is mostly limited by **KV cache + concurrency**. Main design levers:

| Lever | Effect |
|-------|--------|
| **Max context (`max_model_len`)** | Lower context → less KV cache → higher concurrency. |
| **Concurrency cap (`max_num_seqs`)** | More sequences → higher throughput until KV cache/VRAM causes OOM or p95 latency spikes. |
| **Token budget per step (`max_num_batched_tokens`)** | Increasing improves throughput but can worsen token latency. |
| **Micro-batching window** | A small delay (e.g. 10–30 ms) to collect requests into a batch. |

---

## Getting started — Milestone 1 (baseline serving)

1. **Install vLLM** (GPU with CUDA required):
   ```bash
   pip install vllm
   # or from repo: pip install -e ".[worker]"
   ```

2. **Start the vLLM worker** (in one terminal):
   ```bash
   ./scripts/run_vllm_worker.sh
   ```
   Uses `Qwen/Qwen2.5-0.5B-Instruct` by default with `--max-model-len 512` and `--gpu-memory-utilization 0.9`. Override with `VLLM_MODEL` or pass the model as first argument.

3. **Run the smoke test** (in another terminal):
   ```bash
   ./scripts/smoke_test.sh
   ```
   Sends one chat completion request and verifies the response.

See **[docs/vllm-serve-args.md](docs/vllm-serve-args.md)** for CLI argument reference.

---

## Milestone 2 — Load-testing harness

1. **Install Locust:** `pip install locust` (or use `requirements.txt`).
2. **Start vLLM** (as above), then run the load test:
   ```bash
   ./scripts/run_loadtest.sh
   ```
   Or run Locust manually (e.g. UI on port 8089 or headless with `-u`, `-r`, `--run-time`). See **[loadtest/README.md](loadtest/README.md)** for options, ramp-up shape, and how to read **RPS**, **p50/p95 latency**, and **error rate**.

---

## Milestone 3 — Observability

1. **Start vLLM** (as above), then **start monitoring**:
   ```bash
   ./scripts/run_monitoring.sh
   ```
2. **Access:**
   - Prometheus: http://localhost:9090
   - Grafana: http://localhost:3000 (admin/admin)
3. Dashboard **"vLLM Lab — M3 Observability"** shows: latency (p50/p95), RPS, queue depth, in-flight requests, worker state, success counters.

See **[docs/milestone3-guide.md](docs/milestone3-guide.md)** for detailed implementation guide (Vietnamese).

---

## Project Structure (Planned)

See **[docs/plan.md](docs/plan.md)** for the full milestone to-do list, detailed directory layout, conventions, and critical review. Summary:

- **`src/llm_throughput_lab/`** — gateway, supervisor, queue, client, observability
- **`configs/`** — model profiles and fixed prompts
- **`infra/`** — Docker, Compose, Prometheus, Grafana
- **`loadtest/`** — Locust/k6 scenarios
- **`experiments/`** — benchmark run outputs
- **`scripts/`** — bench, grid tuning, smoke test
- **`docs/`** — plan, SLO, tuning notes

