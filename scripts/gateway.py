#!/usr/bin/env python3
"""
Milestone 5 + 6 + 7: Gateway with micro-batching, scale-to-zero supervisor,
admission control, and degradation ladder.

Usage:
  python scripts/gateway.py
  ENABLE_SUPERVISOR=1 python scripts/gateway.py   # M6: auto start/stop worker
  Q_MAX=64 python scripts/gateway.py              # M7: admission limit

Env:
  BATCH_WINDOW_MS   Delay before forwarding (0, 20, 50)
  VLLM_URL          vLLM worker URL (default http://localhost:8000)
  GATEWAY_PORT      Gateway port (default 8001)
  ENABLE_SUPERVISOR 1 = scale-to-zero (start worker on demand, stop after idle)
  IDLE_TIMEOUT_SEC  Idle seconds before stopping worker (default 180)
  Q_MAX             Max queue depth before 429 (default 128)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# Config
BATCH_WINDOW_MS = int(os.environ.get("BATCH_WINDOW_MS", "0"))
VLLM_URL = os.environ.get("VLLM_URL", "http://localhost:8000").rstrip("/")
GATEWAY_PORT = int(os.environ.get("GATEWAY_PORT", "8001"))
ENABLE_SUPERVISOR = os.environ.get("ENABLE_SUPERVISOR", "").lower() in ("1", "true", "yes")
IDLE_TIMEOUT_SEC = float(os.environ.get("IDLE_TIMEOUT_SEC", "180"))
Q_MAX = int(os.environ.get("Q_MAX", "128"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def _lifespan(app: FastAPI):
    global _supervisor
    if ENABLE_SUPERVISOR:
        from scripts.supervisor import Supervisor
        _supervisor = Supervisor(
            worker_url=VLLM_URL,
            idle_timeout_sec=IDLE_TIMEOUT_SEC,
        )
        _supervisor.start_background_loop()
        logger.info("Supervisor enabled (scale-to-zero), idle_timeout=%ss", IDLE_TIMEOUT_SEC)
    yield
    if _supervisor is not None:
        _supervisor.stop_background_loop()
        _supervisor = None


app = FastAPI(title="LLM Gateway (M5+M6+M7)", lifespan=_lifespan)


@dataclass
class PendingRequest:
    """Request waiting in batching queue."""

    body: dict[str, Any]
    received_at: float
    future: asyncio.Future


# Queue and state
_pending: deque[PendingRequest] = deque()
_flush_task: asyncio.Task | None = None
_lock = asyncio.Lock()
_in_flight = 0
_supervisor = None
_worker_ready_timeout = 300  # max seconds to wait for worker on cold start


def _get_queue_depth() -> int:
    """Queue depth = pending in batch queue + in-flight."""
    return len(_pending) + _in_flight


async def _forward_to_vllm(client: httpx.AsyncClient, body: dict) -> tuple[int, dict]:
    """Forward single request to vLLM, return (status_code, response_json)."""
    try:
        r = await client.post(
            f"{VLLM_URL}/v1/chat/completions",
            json=body,
            timeout=120.0,
        )
        return r.status_code, r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    except Exception as e:
        return 500, {"error": str(e)}


async def _ensure_worker_ready() -> bool:
    """If supervisor enabled, wait until worker is ready (or timeout). Returns True if ready."""
    if not ENABLE_SUPERVISOR or _supervisor is None:
        return True
    if _supervisor.is_ready():
        return True
    for _ in range(_worker_ready_timeout):
        await asyncio.sleep(1)
        if _supervisor.is_ready():
            return True
    return False


async def _flush_batch():
    """Flush all pending requests: forward to vLLM in parallel."""
    global _pending, _in_flight
    async with _lock:
        batch = list(_pending)
        _pending.clear()
    if not batch:
        return
    _in_flight += len(batch)
    try:
        async with httpx.AsyncClient() as client:
            tasks = [_forward_to_vllm(client, p.body) for p in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        for req, res in zip(batch, results):
            if isinstance(res, Exception):
                req.future.set_result(JSONResponse({"error": str(res)}, status_code=500))
            else:
                status, data = res
                req.future.set_result(JSONResponse(content=data, status_code=status))
    finally:
        _in_flight -= len(batch)


def _schedule_flush():
    """Schedule a flush after BATCH_WINDOW_MS."""
    global _flush_task

    async def _delayed_flush():
        await asyncio.sleep(BATCH_WINDOW_MS / 1000.0)
        await _flush_batch()

    _flush_task = asyncio.create_task(_delayed_flush())


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """Proxy to vLLM with admission, degradation, optional batching and supervisor."""
    body = await request.json()

    queue_depth = _get_queue_depth()

    # M7: Admission control
    from scripts.policies import check_admission, apply_degradation
    admission = check_admission(queue_depth, q_max=Q_MAX)
    if not admission.admitted:
        return JSONResponse(
            status_code=429,
            content={"error": "overload", "reason": admission.reason},
            headers={"Retry-After": str(admission.retry_after_sec)},
        )

    # M6: Supervisor activity + wait for worker ready (cold start)
    if ENABLE_SUPERVISOR and _supervisor is not None:
        _supervisor.request_activity()
        _supervisor.start_if_needed()
        if not await _ensure_worker_ready():
            return JSONResponse(
                status_code=503,
                content={"error": "worker not ready", "message": "cold start timeout"},
                headers={"Retry-After": "60"},
            )

    # M7: Degradation
    body, tier = apply_degradation(body, queue_depth)

    if BATCH_WINDOW_MS <= 0:
        global _in_flight
        _in_flight += 1
        try:
            async with httpx.AsyncClient() as client:
                status, data = await _forward_to_vllm(client, body)
            return JSONResponse(content=data, status_code=status)
        finally:
            _in_flight -= 1

    loop = asyncio.get_running_loop()
    future: asyncio.Future = loop.create_future()
    async with _lock:
        _pending.append(PendingRequest(body=body, received_at=time.time(), future=future))
        if _flush_task is None or _flush_task.done():
            _schedule_flush()
    return await future


@app.get("/health")
async def health():
    """Health check."""
    out = {"status": "ok", "batch_window_ms": BATCH_WINDOW_MS}
    if ENABLE_SUPERVISOR and _supervisor is not None:
        out["worker_state"] = _supervisor.state.value
    return out


@app.get("/metrics")
async def metrics():
    """Prometheus-style metrics for queue, worker state, in-flight (M3/M6/M7)."""
    lines = [
        "# HELP gateway_queue_depth Total requests in queue + in-flight (drives admission, degradation)",
        "# TYPE gateway_queue_depth gauge",
        f"gateway_queue_depth {_get_queue_depth()}",
        "# HELP gateway_in_flight Requests currently being processed by worker",
        "# TYPE gateway_in_flight gauge",
        f"gateway_in_flight {_in_flight}",
        "# HELP gateway_pending_batch Requests waiting in batching window",
        "# TYPE gateway_pending_batch gauge",
        f"gateway_pending_batch {len(_pending)}",
    ]
    if ENABLE_SUPERVISOR and _supervisor is not None:
        state_val = {"idle": 0, "starting": 1, "running": 2, "stopping": 3}.get(_supervisor.state.value, -1)
        lines.extend([
            "# HELP gateway_worker_state 0=idle 1=starting 2=running 3=stopping (scale-to-zero)",
            "# TYPE gateway_worker_state gauge",
            f"gateway_worker_state {state_val}",
        ])
    return "\n".join(lines) + "\n"


@app.get("/v1/models")
async def models():
    """Proxy to vLLM models list."""
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{VLLM_URL}/v1/models", timeout=10.0)
    return JSONResponse(content=r.json(), status_code=r.status_code)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=GATEWAY_PORT)
