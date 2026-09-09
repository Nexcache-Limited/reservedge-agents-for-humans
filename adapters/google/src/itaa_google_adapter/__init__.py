"""Google competition adapter. Models extract or explain; code owns governance."""

from __future__ import annotations

ADAPTER_VERSION = "0.8.2"
DEFAULT_MODEL_NAME = "gemini-2.5-flash"
DEFAULT_REGION = "us-central1"
EXTRACT_TEMPLATE_VERSION = "wp08.extract.v3"
EXPLAIN_TEMPLATE_VERSION = "wp08.explain.v1"

__all__ = [
    "ADAPTER_VERSION",
    "DEFAULT_MODEL_NAME",
    "DEFAULT_REGION",
    "EXTRACT_TEMPLATE_VERSION",
    "EXPLAIN_TEMPLATE_VERSION",
]
