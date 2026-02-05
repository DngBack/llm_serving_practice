#!/usr/bin/env python3
"""
Milestone 6: Spawn and control vLLM worker process (scale-to-zero).

Builds the same command as run_vllm_worker.sh so the worker runs with
identical args (model, max-model-len, max-num-seqs, etc.).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _build_vllm_cmd() -> list[str]:
    """Build vllm serve command from env (mirror run_vllm_worker.sh)."""
    model = os.environ.get("VLLM_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")
    host = os.environ.get("VLLM_HOST", "0.0.0.0")
    port = os.environ.get("VLLM_PORT", "8000")
    max_num_seqs = os.environ.get("VLLM_MAX_NUM_SEQS", "64")
    gpu_mem = os.environ.get("VLLM_GPU_MEMORY_UTILIZATION", "0.85")
    max_batched = os.environ.get("VLLM_MAX_NUM_BATCHED_TOKENS", "")
    chunked = os.environ.get("VLLM_ENABLE_CHUNKED_PREFILL", "true").lower() in ("true", "1", "yes")

    vllm_exe = shutil.which("vllm")
    if vllm_exe:
        base = [vllm_exe, "serve", model]
    else:
        base = [sys.executable, "-m", "vllm", "serve", model]

    args = base + [
        "--host", host,
        "--port", port,
        "--max-model-len", "512",
        "--max-num-seqs", max_num_seqs,
        "--gpu-memory-utilization", gpu_mem,
    ]
    if max_batched:
        args.extend(["--max-num-batched-tokens", max_batched])
    if chunked:
        args.append("--enable-chunked-prefill")
    return args


class WorkerProcess:
    """Start/stop vLLM worker as a subprocess."""

    def __init__(self) -> None:
        self._process: subprocess.Popen | None = None

    def start(self) -> None:
        """Start vLLM worker subprocess. Idempotent: no-op if already running."""
        if self._process is not None and self._process.poll() is None:
            return
        env = os.environ.copy()
        env.setdefault("VLLM_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")
        cmd = _build_vllm_cmd()
        self._process = subprocess.Popen(
            cmd,
            cwd=str(REPO_ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

    def stop(self) -> None:
        """Terminate worker process. Idempotent."""
        if self._process is None:
            return
        try:
            self._process.terminate()
            try:
                self._process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=10)
        except Exception:
            pass
        self._process = None

    def is_alive(self) -> bool:
        """Return True if process is running."""
        if self._process is None:
            return False
        return self._process.poll() is None

    def get_pid(self) -> int | None:
        """Return process PID or None."""
        if self._process is None:
            return None
        return self._process.pid
