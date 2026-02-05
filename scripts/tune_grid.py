#!/usr/bin/env python3
"""
Milestone 4: Grid search for throughput optimization.

Sweep max_num_seqs × max_num_batched_tokens, run load test for each config,
record RPS, p50/p95, error rate. Output best point against SLO.

Usage:
  # Mode 1: Run load test for current vLLM config (env vars), append to results
  python scripts/tune_grid.py --single

  # Mode 2: Full grid - spawn vLLM per config, run load test, record (long-running)
  python scripts/tune_grid.py [--quick]

  # Mode 3: Run load test only (vLLM already running), save to specific file
  python scripts/tune_grid.py --run-loadtest --config-name my_config

Env:
  QUICK=1              Use 1 min run per config (default 10 min)
  SLO_P95_MS=5000      p95 latency SLO in ms (default 5000)
  SLO_ERROR_RATE=0.001 Max error rate (default 0.001)
  VLLM_*               Passed to run_vllm_worker.sh in full-grid mode
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Grid: max_num_seqs × max_num_batched_tokens (plan.md M4)
GRID_MAX_NUM_SEQS = [64, 128, 192, 256]
GRID_MAX_NUM_BATCHED_TOKENS = [4096, 8192, 12288, 16384]

REPO_ROOT = Path(__file__).resolve().parent.parent
LOADTEST_DIR = REPO_ROOT / "loadtest"
OUT_DIR = REPO_ROOT / "experiments" / "runs"
RUN_SCRIPT = REPO_ROOT / "scripts" / "run_vllm_worker.sh"
LOADTEST_SCRIPT = REPO_ROOT / "scripts" / "run_loadtest.sh"


def load_profile(profile_name: str) -> dict:
    """Load model profile from configs/model_profiles/<name>.yaml."""
    path = REPO_ROOT / "configs" / "model_profiles" / f"{profile_name}.yaml"
    if not path.exists():
        return {}
    try:
        import yaml

        return yaml.safe_load(path.read_text()) or {}
    except ImportError:
        # Fallback: parse minimal YAML manually
        data = {}
        for line in path.read_text().splitlines():
            if ":" in line and not line.strip().startswith("#"):
                k, v = line.split(":", 1)
                v = v.strip()
                if v.lower() == "true":
                    v = True
                elif v.lower() == "false":
                    v = False
                elif v.isdigit():
                    v = int(v)
                elif v.replace(".", "").isdigit():
                    v = float(v)
                data[k.strip()] = v
        return data


def parse_locust_stats(csv_path: Path) -> dict | None:
    """Parse Locust stats CSV, return RPS, p50, p95, error_rate."""
    if not csv_path.exists():
        return None
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("Name") == "Aggregated":
                try:
                    req_count = int(row.get("Request Count", 0))
                    fail_count = int(row.get("Failure Count", 0))
                    rps = float(row.get("Requests/s", 0))
                    p50 = float(row.get("50%", 0))
                    p95 = float(row.get("95%", 0))
                    return {
                        "request_count": req_count,
                        "failure_count": fail_count,
                        "rps": rps,
                        "p50_ms": p50,
                        "p95_ms": p95,
                        "error_rate": fail_count / req_count if req_count else 0,
                    }
                except (ValueError, KeyError):
                    return None
    return None


def run_loadtest(
    base_url: str = "http://localhost:8000",
    runtime: str | None = None,
    out_prefix: str | None = None,
) -> Path | None:
    """Run Locust load test, return path to stats CSV."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    quick = os.environ.get("QUICK", "").lower() in ("1", "true", "yes")
    runtime = runtime or ("1m" if quick else "10m")
    timestamp = time.strftime("%Y-%m-%d_%H%M%S")
    prefix = out_prefix or f"locust_{timestamp}"
    csv_prefix = OUT_DIR / prefix

    env = os.environ.copy()
    env["LOADTEST_RUNTIME"] = runtime

    cmd = [
        "locust",
        "-f",
        str(LOADTEST_DIR / "locustfile.py"),
        "--host",
        base_url,
        "--headless",
        "-u",
        "20",
        "-r",
        "2",
        "--run-time",
        runtime,
        "--csv",
        str(csv_prefix),
        "--html",
        str(csv_prefix) + "_report.html",
        "--skip-log-setup",
    ]

    result = subprocess.run(cmd, cwd=LOADTEST_DIR, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        return None

    stats_path = Path(str(csv_prefix) + "_stats.csv")
    return stats_path if stats_path.exists() else None


def wait_for_vllm(url: str = "http://localhost:8000", timeout: float = 120) -> bool:
    """Wait for vLLM to be ready (GET /v1/models)."""
    try:
        import urllib.request

        start = time.time()
        while time.time() - start < timeout:
            try:
                req = urllib.request.Request(f"{url}/v1/models", method="GET")
                with urllib.request.urlopen(req, timeout=5) as r:
                    if r.status == 200:
                        return True
            except OSError:
                pass
            time.sleep(2)
    except ImportError:
        # Fallback: use curl
        start = time.time()
        while time.time() - start < timeout:
            r = subprocess.run(
                ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", f"{url}/v1/models"],
                capture_output=True,
                text=True,
            )
            if r.returncode == 0 and r.stdout.strip() == "200":
                return True
            time.sleep(2)
    return False


def run_single_config(
    config: dict,
    base_url: str = "http://localhost:8000",
    config_name: str = "single",
) -> dict | None:
    """Run load test for one config (vLLM must already be running with this config)."""
    print(f"Running load test for config: {config_name}")
    stats_path = run_loadtest(base_url=base_url, out_prefix=f"grid_{config_name}_{int(time.time())}")
    if not stats_path:
        return None
    metrics = parse_locust_stats(stats_path)
    if metrics:
        metrics["config"] = config
        metrics["config_name"] = config_name
        print(f"  RPS={metrics['rps']:.2f} p95={metrics['p95_ms']:.0f}ms error={metrics['error_rate']:.4f}")
    return metrics


def run_full_grid(
    base_url: str = "http://localhost:8000",
    quick: bool = False,
    slo_p95_ms: float = 5000,
    slo_error_rate: float = 0.001,
) -> list[dict]:
    """Run full grid: spawn vLLM per config, run load test, record."""
    runtime = "1m" if quick else "10m"
    results = []

    # Reduce grid for quick mode
    seqs = GRID_MAX_NUM_SEQS if not quick else [64, 128]
    tokens = GRID_MAX_NUM_BATCHED_TOKENS if not quick else [4096, 8192]

    for max_num_seqs in seqs:
        for max_num_batched_tokens in tokens:
            config_name = f"seq{max_num_seqs}_tok{max_num_batched_tokens}"
            env = os.environ.copy()
            env["VLLM_MAX_NUM_SEQS"] = str(max_num_seqs)
            env["VLLM_MAX_NUM_BATCHED_TOKENS"] = str(max_num_batched_tokens)
            env["VLLM_ENABLE_CHUNKED_PREFILL"] = "true"
            env["LOADTEST_RUNTIME"] = runtime

            print(f"\n--- Config: max_num_seqs={max_num_seqs} max_num_batched_tokens={max_num_batched_tokens} ---")

            proc = subprocess.Popen(
                ["bash", str(RUN_SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )

            if not wait_for_vllm(base_url, timeout=180):
                print("  vLLM failed to start (timeout)")
                proc.terminate()
                proc.wait(timeout=10)
                results.append(
                    {
                        "config": {"max_num_seqs": max_num_seqs, "max_num_batched_tokens": max_num_batched_tokens},
                        "config_name": config_name,
                        "error": "vLLM startup timeout",
                    }
                )
                continue

            stats_path = run_loadtest(base_url=base_url, runtime=runtime, out_prefix=f"grid_{config_name}_{int(time.time())}")
            proc.terminate()
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()

            if stats_path:
                metrics = parse_locust_stats(stats_path)
                if metrics:
                    metrics["config"] = {"max_num_seqs": max_num_seqs, "max_num_batched_tokens": max_num_batched_tokens}
                    metrics["config_name"] = config_name
                    within_slo = metrics["p95_ms"] <= slo_p95_ms and metrics["error_rate"] <= slo_error_rate
                    metrics["within_slo"] = within_slo
                    results.append(metrics)
                    print(f"  RPS={metrics['rps']:.2f} p95={metrics['p95_ms']:.0f}ms within_slo={within_slo}")

    return results


def main():
    parser = argparse.ArgumentParser(description="M4 Grid search for throughput optimization")
    parser.add_argument("--single", action="store_true", help="Run load test once for current vLLM config")
    parser.add_argument("--run-loadtest", action="store_true", help="Run load test only (vLLM must be running)")
    parser.add_argument("--config-name", default="manual", help="Config name for output")
    parser.add_argument("--quick", action="store_true", help="Short run (1 min per config)")
    parser.add_argument("--base-url", default="http://localhost:8000", help="vLLM or gateway URL")
    parser.add_argument("--profile", default="throughput", help="Model profile to load (for --single)")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.run_loadtest or args.single:
        config = load_profile(args.profile) if args.single else {}
        metrics = run_single_config(config, base_url=args.base_url, config_name=args.config_name)
        if metrics:
            out_file = OUT_DIR / f"grid_{args.config_name}_{int(time.time())}.json"
            out_file.write_text(json.dumps(metrics, indent=2))
            print(f"Saved: {out_file}")
        return 0 if metrics else 1

    # Full grid
    quick = args.quick or os.environ.get("QUICK", "").lower() in ("1", "true", "yes")
    slo_p95 = float(os.environ.get("SLO_P95_MS", "5000"))
    slo_err = float(os.environ.get("SLO_ERROR_RATE", "0.001"))

    results = run_full_grid(base_url=args.base_url, quick=quick, slo_p95_ms=slo_p95, slo_error_rate=slo_err)

    valid = [r for r in results if r.get("within_slo") and "error" not in r]
    best = max(valid, key=lambda x: x["rps"]) if valid else None

    timestamp = time.strftime("%Y-%m-%d_%H%M%S")
    out_file = OUT_DIR / f"grid_full_{timestamp}.json"
    out_file.write_text(json.dumps({"results": results, "best": best, "slo_p95_ms": slo_p95}, indent=2))

    print(f"\n--- Results saved: {out_file} ---")
    if best:
        print(f"Best (within SLO): {best['config_name']} RPS={best['rps']:.2f} p95={best['p95_ms']:.0f}ms")
    else:
        print("No config within SLO. Check results for OOM or latency.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
