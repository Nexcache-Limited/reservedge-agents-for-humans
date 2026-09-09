"""AWS competition adapter. Strands plans; code owns governance."""

from __future__ import annotations

ADAPTER_VERSION = "0.1.0"
DEFAULT_LIVE_MODEL = "global.anthropic.claude-sonnet-4-6"
PLAN_QUESTION_CAP = 3

__all__ = [
    "ADAPTER_VERSION",
    "DEFAULT_LIVE_MODEL",
    "PLAN_QUESTION_CAP",
]
