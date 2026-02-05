#!/usr/bin/env bash
# v2: vLLM worker entrypoint — mirrors scripts/run_vllm_worker.sh
set -e

MODEL="${VLLM_MODEL:-Qwen/Qwen2.5-0.5B-Instruct}"
HOST="${VLLM_HOST:-0.0.0.0}"
PORT="${VLLM_PORT:-8000}"
MAX_NUM_SEQS="${VLLM_MAX_NUM_SEQS:-64}"
GPU_MEM_UTIL="${VLLM_GPU_MEMORY_UTILIZATION:-0.85}"
MAX_NUM_BATCHED_TOKENS="${VLLM_MAX_NUM_BATCHED_TOKENS:-}"
ENABLE_CHUNKED="${VLLM_ENABLE_CHUNKED_PREFILL:-true}"

EXTRA_ARGS=()
[ -n "${MAX_NUM_BATCHED_TOKENS}" ] && EXTRA_ARGS+=(--max-num-batched-tokens "${MAX_NUM_BATCHED_TOKENS}")
[ "${ENABLE_CHUNKED}" = "true" ] && EXTRA_ARGS+=(--enable-chunked-prefill)

exec vllm serve "${MODEL}" \
  --host "${HOST}" \
  --port "${PORT}" \
  --max-model-len 512 \
  --max-num-seqs "${MAX_NUM_SEQS}" \
  --gpu-memory-utilization "${GPU_MEM_UTIL}" \
  "${EXTRA_ARGS[@]}"
