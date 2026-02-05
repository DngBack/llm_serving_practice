#!/usr/bin/env python3
"""
Milestone 5: Gateway with micro-batching window.

Proxy /v1/chat/completions to vLLM worker. Collect requests for BATCH_WINDOW_MS
before forwarding, so vLLM receives them in a burst and can batch (continuous batching).

Usage:
  BATCH_WINDOW_MS=20 python scripts/gateway.py
  # or: uvicorn scripts.gateway:app --host 0.0.0.0 --port 8001

Env:
  BATCH_WINDOW_MS   Delay before forwarding (0=no delay, 20, 50 for A/B test)
  VLLM_URL          vLLM worker URL (default http://localhost:8000)
  GATEWAY_PORT      Gateway port (default 8001)
"""

from __future__ import annotations

import asyncio
import os
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# Config
BATCH_WINDOW_MS = int(os.environ.get("BATCH_WINDOW_MS", "0"))
VLLM_URL = os.environ.get("VLLM_URL", "http://localhost:8000").rstrip("/")
GATEWAY_PORT = int(os.environ.get("GATEWAY_PORT", "8001"))

app = FastAPI(title="LLM Gateway (M5 Batching)")


@dataclass
class PendingRequest:
    """Request waiting in batching queue."""

    body: dict[str, Any]
    received_at: float
    future: asyncio.Future


# Queue of requests waiting to be batched
_pending: deque[PendingRequest] = deque()
_flush_task: asyncio.Task | None = None
_lock = asyncio.Lock()


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


async def _flush_batch():
    """Flush all pending requests: forward to vLLM in parallel."""
    global _pending
    async with _lock:
        batch = list(_pending)
        _pending.clear()
    if not batch:
        return
    async with httpx.AsyncClient() as client:
        tasks = [_forward_to_vllm(client, p.body) for p in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    for i, (req, res) in enumerate(zip(batch, results)):
        if isinstance(res, Exception):
            req.future.set_result(JSONResponse({"error": str(res)}, status_code=500))
        else:
            status, data = res
            req.future.set_result(JSONResponse(content=data, status_code=status))


def _schedule_flush():
    """Schedule a flush after BATCH_WINDOW_MS."""
    global _flush_task

    async def _delayed_flush():
        await asyncio.sleep(BATCH_WINDOW_MS / 1000.0)
        await _flush_batch()

    _flush_task = asyncio.create_task(_delayed_flush())


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """Proxy to vLLM with optional batching window."""
    body = await request.json()

    if BATCH_WINDOW_MS <= 0:
        async with httpx.AsyncClient() as client:
            status, data = await _forward_to_vllm(client, body)
        return JSONResponse(content=data, status_code=status)

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
    return {"status": "ok", "batch_window_ms": BATCH_WINDOW_MS}


@app.get("/v1/models")
async def models():
    """Proxy to vLLM models list."""
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{VLLM_URL}/v1/models", timeout=10.0)
    return JSONResponse(content=r.json(), status_code=r.status_code)