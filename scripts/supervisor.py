#!/usr/bin/env python3
"""
Milestone 6: Supervisor state machine for scale-to-zero.

- States: idle -> starting -> running -> (idle_timeout) -> stopping -> idle
- Start worker when queue_depth > 0 (or on first request)
- Stop worker when idle for idle_timeout (default 180s)
- Healthcheck (HTTP) to know when worker is READY
"""

from __future__ import annotations

import asyncio
import enum
import logging
import time
from typing import Callable

import httpx

from scripts.worker_process import WorkerProcess

logger = logging.getLogger(__name__)


class WorkerState(str, enum.Enum):
    IDLE = "idle"           # No process
    STARTING = "starting"   # Process started, waiting for healthcheck
    RUNNING = "running"     # Healthcheck OK
    STOPPING = "stopping"   # Shutting down process


class Supervisor:
    """State machine: start worker on demand, stop after idle_timeout."""

    def __init__(
        self,
        worker_url: str = "http://localhost:8000",
        idle_timeout_sec: float = 180.0,
        healthcheck_interval_sec: float = 2.0,
        idle_check_interval_sec: float = 15.0,
    ) -> None:
        self.worker_url = worker_url.rstrip("/")
        self.idle_timeout_sec = idle_timeout_sec
        self.healthcheck_interval_sec = healthcheck_interval_sec
        self.idle_check_interval_sec = idle_check_interval_sec
        self._worker = WorkerProcess()
        self._state = WorkerState.IDLE
        self._last_request_time: float | None = None
        self._task: asyncio.Task | None = None
        self._state_changed: asyncio.Event | None = None  # set by gateway for wait_until_ready

    @property
    def state(self) -> WorkerState:
        return self._state

    def request_activity(self) -> None:
        """Call when a request is received (for idle timeout)."""
        self._last_request_time = time.monotonic()

    def start_if_needed(self) -> bool:
        """
        If idle, transition to starting and spawn worker.
        Returns True if we started (or are starting), False if already running/stopping.
        """
        if self._state == WorkerState.RUNNING or self._state == WorkerState.STARTING:
            return True
        if self._state == WorkerState.STOPPING:
            return False
        # IDLE -> STARTING
        self._state = WorkerState.STARTING
        self._worker.start()
        self._last_request_time = time.monotonic()
        logger.info("Supervisor: state=STARTING, worker process started (pid=%s)", self._worker.get_pid())
        return True

    async def healthcheck(self) -> bool:
        """Return True if worker responds (e.g. /v1/models)."""
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"{self.worker_url}/v1/models",
                    timeout=5.0,
                )
                return r.status_code == 200
        except Exception as e:
            logger.debug("Healthcheck failed: %s", e)
            return False

    async def run_loop(self) -> None:
        """
        Background loop: poll health when starting, check idle when running.
        """
        while True:
            try:
                if self._state == WorkerState.STARTING:
                    if await self.healthcheck():
                        self._state = WorkerState.RUNNING
                        logger.info("Supervisor: state=RUNNING, worker ready")
                        if self._state_changed:
                            self._state_changed.set()
                    await asyncio.sleep(self.healthcheck_interval_sec)

                elif self._state == WorkerState.RUNNING:
                    if not self._worker.is_alive():
                        self._state = WorkerState.IDLE
                        logger.warning("Supervisor: worker died, state=IDLE")
                        continue
                    # Idle timeout
                    if self._last_request_time is not None:
                        elapsed = time.monotonic() - self._last_request_time
                        if elapsed >= self.idle_timeout_sec:
                            logger.info("Supervisor: idle %.0fs >= %s, stopping worker", elapsed, self.idle_timeout_sec)
                            self._state = WorkerState.STOPPING
                            await asyncio.get_event_loop().run_in_executor(None, self._worker.stop)
                            self._state = WorkerState.IDLE
                            logger.info("Supervisor: state=IDLE")
                    await asyncio.sleep(self.idle_check_interval_sec)

                elif self._state == WorkerState.STOPPING:
                    await asyncio.sleep(1.0)

                else:
                    # IDLE
                    await asyncio.sleep(self.idle_check_interval_sec)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("Supervisor loop error: %s", e)
                await asyncio.sleep(5.0)

    def start_background_loop(self, state_changed: asyncio.Event | None = None) -> None:
        """Start the supervisor background task."""
        self._state_changed = state_changed
        self._task = asyncio.create_task(self.run_loop())
        logger.info("Supervisor background loop started")

    def stop_background_loop(self) -> None:
        """Cancel the background loop and stop worker."""
        if self._task and not self._task.done():
            self._task.cancel()
        self._worker.stop()
        self._state = WorkerState.IDLE

    def is_ready(self) -> bool:
        """True if worker is RUNNING (ready to serve)."""
        return self._state == WorkerState.RUNNING
