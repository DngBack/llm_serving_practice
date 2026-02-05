"""
Fixed 200-in / 200-out scenario for throughput benchmarking (Milestone 2).

- Prompt: loaded from configs/prompts/prompt_200.txt (~200 tokens target).
- Output: max_tokens=200, temperature=0 for deterministic, comparable runs.
"""

import os
from pathlib import Path


def get_project_root() -> Path:
    """Project root: assume we run from repo root or loadtest/."""
    cwd = Path.cwd()
    if (cwd / "configs" / "prompts").exists():
        return cwd
    if (cwd.parent / "configs" / "prompts").exists():
        return cwd.parent
    return cwd


def load_prompt_200() -> str:
    """Load prompt from configs/prompts/prompt_200.txt. Fallback if file missing."""
    root = get_project_root()
    path = root / "configs" / "prompts" / "prompt_200.txt"
    if path.exists():
        return path.read_text().strip()
    # Fallback: short prompt (for CI or when config not present)
    return (
        "You are a helpful assistant. Answer concisely in one or two short paragraphs. "
        "Do not use bullet points unless asked. "
        "Repeat the following line exactly 10 times: The quick brown fox jumps over the lazy dog. "
    )


# Fixed request payload for 200/200 workload (temperature=0, max_tokens=200)
def get_messages(prompt: str | None = None) -> list[dict]:
    """Messages for /v1/chat/completions. One user message with prompt_200 content."""
    content = (prompt or load_prompt_200()).strip() or "Say hello in one sentence."
    return [{"role": "user", "content": content}]


def get_request_kwargs(prompt: str | None = None) -> dict:
    """kwargs for OpenAI-style chat completion (200 out, temp=0)."""
    return {
        "model": "",
        "messages": get_messages(prompt=prompt),
        "max_tokens": 200,
        "temperature": 0,
    }
