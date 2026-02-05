"""
Milestone 2: Load-test harness for vLLM (OpenAI-compatible) server.

- Constant arrival rate with gradual ramp-up.
- Fixed workload: 200 input tokens (prompt_200.txt) / 200 output tokens, temperature=0.
- Metrics: RPS, p50/p95 latency, error rate (from Locust stats + optional JSON report).

Usage (vLLM must be running on localhost:8000):
  locust -f loadtest/locustfile.py --host=http://localhost:8000
  # Headless, 10 min run, 20 users, spawn 2/sec, then open HTML report:
  locust -f loadtest/locustfile.py --host=http://localhost:8000 \
    --headless -u 20 -r 2 --run-time 10m
  # With ramp-up shape (see RampUpThenConstant shape below):
  locust -f loadtest/locustfile.py --host=http://localhost:8000 \
    --headless --run-time 10m
"""

import os
from locust import HttpUser, task

# Import fixed 200/200 scenario
from scenarios.fixed_200_200 import get_request_kwargs

# Base URL; override with --host when launching Locust
HOST = os.environ.get("LOCUST_HOST", "http://localhost:8000")


class Fixed200200User(HttpUser):
    """One user = repeated requests with fixed 200-in/200-out payload."""

    abstract = False

    def on_start(self):
        self.payload = get_request_kwargs()

    @task(1)
    def chat_200_200(self):
        """POST /v1/chat/completions with fixed prompt and max_tokens=200, temperature=0."""
        self.client.post(
            "/v1/chat/completions",
            json=self.payload,
            name="/v1/chat/completions [200/200]",
        )


# --- Ramp-up then constant load (optional) ---
# Set USE_RAMP_SHAPE=1 to use this shape; otherwise use -u and -r for fixed users.

try:
    from locust import LoadTestShape
except ImportError:
    LoadTestShape = None

if LoadTestShape is not None and os.environ.get("USE_RAMP_SHAPE", "").lower() in (
    "1",
    "true",
    "yes",
):

    class RampUpThenConstantShape(LoadTestShape):
        """Ramp up users over ramp_sec, then hold constant (M0 sustained run)."""
        ramp_sec = int(os.environ.get("LOCUST_RAMP_SEC", "60"))
        min_users = int(os.environ.get("LOCUST_MIN_USERS", "2"))
        max_users = int(os.environ.get("LOCUST_MAX_USERS", "20"))
        spawn_rate = float(os.environ.get("LOCUST_SPAWN_RATE", "2"))

        def tick(self):
            run = self.get_run_time()
            if run is None:
                return None
            elapsed = run
            if elapsed < self.ramp_sec:
                progress = elapsed / self.ramp_sec
                target = int(
                    self.min_users + (self.max_users - self.min_users) * progress
                )
                return (target, self.spawn_rate)
            return (self.max_users, self.spawn_rate)
