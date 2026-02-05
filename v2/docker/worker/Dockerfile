# v2: vLLM Worker — GPU inference
# Base: NVIDIA CUDA runtime for GPU support
FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir vllm==0.15.0

# Env defaults (override via K8s Deployment)
ENV VLLM_MODEL=Qwen/Qwen2.5-0.5B-Instruct
ENV VLLM_HOST=0.0.0.0
ENV VLLM_PORT=8000
ENV VLLM_MAX_NUM_SEQS=64
ENV VLLM_GPU_MEMORY_UTILIZATION=0.85
ENV VLLM_ENABLE_CHUNKED_PREFILL=true

EXPOSE 8000

COPY v2/docker/worker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
