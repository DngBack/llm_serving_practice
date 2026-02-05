#!/usr/bin/env python3
"""
Milestone 7: Admission control and degradation ladder.

- If queue_depth > Q_MAX -> return 429 + Retry-After
- Degradation ladder: reduce max_new_tokens, max_model_len, max_num_seqs
  when under load to avoid overload
- Log which degradation tier is active
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Default admission: reject when queue exceeds this (tune from M4 results)
DEFAULT_Q_MAX = 128

# Degradation tiers: (queue_low, queue_high] -> tier
# tier 0: no degradation
# tier 1: max_new_tokens 200 -> 128
# tier 2: also suggest max_model_len 512 -> 448 (applied at worker profile; here we only tweak request)
# tier 3: further reduce (e.g. max_new_tokens 64)
# We apply degradation by modifying the request body (max_tokens). max_model_len/max_num_seqs
# are worker-level; for per-request we only have max_tokens and possibly truncation.


@dataclass
class AdmissionResult:
    """Result of admission check."""
    admitted: bool
    retry_after_sec: int = 60
    reason: str = ""


@dataclass
class DegradationTier:
    """One step in the degradation ladder."""
    tier: int
    max_new_tokens: int
    description: str


# Ladder: tier 0 = normal, 1/2/3 = increasingly degraded
DEGRADATION_LADDER = [
    DegradationTier(0, 200, "normal"),
    DegradationTier(1, 128, "max_new_tokens=128"),
    DegradationTier(2, 96, "max_new_tokens=96"),
    DegradationTier(3, 64, "max_new_tokens=64"),
]


def check_admission(queue_depth: int, q_max: int | None = None) -> AdmissionResult:
    """
    If queue_depth > Q_MAX, reject with 429.
    Returns AdmissionResult(admitted=False, retry_after_sec=...) when rejected.
    """
    limit = q_max if q_max is not None else DEFAULT_Q_MAX
    if queue_depth <= limit:
        return AdmissionResult(admitted=True)
    return AdmissionResult(
        admitted=False,
        retry_after_sec=60,
        reason=f"queue_depth {queue_depth} > Q_MAX {limit}",
    )


def get_degradation_tier(queue_depth: int) -> DegradationTier:
    """
    Choose degradation tier from queue depth.
    Thresholds: 0-32 -> tier 0, 33-64 -> 1, 65-96 -> 2, 97+ -> 3.
    """
    if queue_depth <= 32:
        return DEGRADATION_LADDER[0]
    if queue_depth <= 64:
        return DEGRADATION_LADDER[1]
    if queue_depth <= 96:
        return DEGRADATION_LADDER[2]
    return DEGRADATION_LADDER[3]


def apply_degradation(body: dict[str, Any], queue_depth: int) -> tuple[dict[str, Any], DegradationTier]:
    """
    Copy body and apply degradation (max_tokens) based on queue_depth.
    Returns (modified_body, tier). Logs active tier.
    """
    tier = get_degradation_tier(queue_depth)
    out = copy.deepcopy(body)
    # OpenAI/vLLM: max_tokens in body; apply cap from tier
    current = out.get("max_tokens") if isinstance(out.get("max_tokens"), int) else 200
    if current > tier.max_new_tokens:
        out["max_tokens"] = tier.max_new_tokens
        logger.info("Degradation tier %s active (queue_depth=%s): %s", tier.tier, queue_depth, tier.description)
    return out, tier
