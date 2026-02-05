# v2: Gateway — stateless, proxies to worker Service
# No supervisor (K8s HPA handles scaling)
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

RUN pip install --no-cache-dir \
    fastapi>=0.100.0 \
    uvicorn>=0.22.0 \
    httpx>=0.24.0

# Copy gateway code from v1 (build context = repo root)
RUN mkdir -p /app/scripts
COPY v1/scripts/gateway.py v1/scripts/policies.py /app/scripts/
RUN touch /app/scripts/__init__.py

# V2: No supervisor in container; VLLM_URL points to K8s Service
ENV ENABLE_SUPERVISOR=0
ENV VLLM_URL=http://worker:8000
ENV GATEWAY_PORT=8001
ENV Q_MAX=128
ENV BATCH_WINDOW_MS=0

EXPOSE 8001

CMD ["uvicorn", "scripts.gateway:app", "--host", "0.0.0.0", "--port", "8001"]
