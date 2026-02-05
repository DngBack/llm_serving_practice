# vLLM serve CLI args (Milestone 1)

Reference for the key arguments used in baseline serving on a small GPU.

## Command

```bash
vllm serve <MODEL> [OPTIONS]
```

Example (M1 baseline):

```bash
vllm serve Qwen/Qwen2.5-0.5B-Instruct \
  --host 0.0.0.0 \
  --port 8000 \
  --max-model-len 512 \
  --gpu-memory-utilization 0.9
```

## Key arguments for 4GB GPU

| Argument | M1 value | Description |
|----------|----------|-------------|
| `--max-model-len` | `512` | Model context length (prompt + output). Lower value reduces KV cache and avoids OOM on 4GB. Supports `1k`, `1K`, etc. |
| `--gpu-memory-utilization` | `0.9` | Fraction of GPU memory (0–1) for the model executor. Default is 0.9; use to maximize KV cache while leaving headroom. |

## Other useful args (later milestones)

- **`--port`** — API server port (default `8000`).
- **`--host`** — Bind address (default varies; use `0.0.0.0` for remote access).
- **`--max-num-seqs`** — Max sequences per scheduling step (M4 grid search).
- **`--max-num-batched-tokens`** — Max tokens per step (M4).
- **`--enable-chunked-prefill`** — Allow chunked prefill so decode can run while prefill is in progress (M4).

## API

vLLM serves an **OpenAI-compatible** HTTP API:

- `GET /v1/models` — List models (useful for readiness).
- `POST /v1/chat/completions` — Chat completions (same schema as OpenAI).

Full reference: [vLLM CLI — serve](https://docs.vllm.ai/en/stable/cli/serve/).
