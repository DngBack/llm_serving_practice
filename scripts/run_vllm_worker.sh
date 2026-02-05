#!/usr/bin/env bash
# Milestone 1: Run vLLM serve with baseline settings for small GPU (e.g. 4GB VRAM).
# Usage: ./scripts/run_vllm_worker.sh [MODEL]
#   MODEL defaults to Qwen/Qwen2.5-0.5B-Instruct (or VLLM_MODEL env var).
#
# On ~4GB VRAM, vLLM's sampler warmup uses "256 dummy requests" by default and can OOM.
# We set --max-num-seqs 64 and --gpu-memory-utilization 0.85 to avoid that.

set -e

MODEL="${1:-${VLLM_MODEL:-Qwen/Qwen2.5-0.5B-Instruct}}"
HOST="${VLLM_HOST:-0.0.0.0}"
PORT="${VLLM_PORT:-8000}"

# Conservative for 4GB (and GPUs that report ~3.7 GiB): avoid OOM during sampler warmup
MAX_NUM_SEQS="${VLLM_MAX_NUM_SEQS:-64}"
GPU_MEM_UTIL="${VLLM_GPU_MEMORY_UTILIZATION:-0.85}"

echo "Starting vLLM worker (M1 baseline)"
echo "  Model: ${MODEL}"
echo "  Host:  ${HOST}:${PORT}"
echo "  Args:  --max-model-len 512 --max-num-seqs ${MAX_NUM_SEQS} --gpu-memory-utilization ${GPU_MEM_UTIL}"
echo ""

vllm serve "${MODEL}" \
  --host "${HOST}" \
  --port "${PORT}" \
  --max-model-len 512 \
  --max-num-seqs "${MAX_NUM_SEQS}" \
  --gpu-memory-utilization "${GPU_MEM_UTIL}"
