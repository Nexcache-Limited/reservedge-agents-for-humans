"""Explicit model-mode selection. Does not import Google SDKs."""

from __future__ import annotations

import os
from typing import Literal

from itaa_application.errors import ApplicationError

ModelMode = Literal["fake", "live"]

ENV_MODEL_MODE = "ITAA_GOOGLE_MODEL_MODE"
ENV_LIVE_ALIAS = "ITAA_GOOGLE_LIVE"
ENV_LIVE_TEST = "ITAA_GOOGLE_LIVE_TEST"
MODE_FAKE: ModelMode = "fake"
MODE_LIVE: ModelMode = "live"
CLOSED_MODES: frozenset[str] = frozenset({MODE_FAKE, MODE_LIVE})


def raw_model_mode() -> str:
    raw = os.environ.get(ENV_MODEL_MODE)
    if raw is None or raw.strip() == "":
        if os.environ.get(ENV_LIVE_ALIAS) == "1":
            return MODE_LIVE
        return MODE_FAKE
    return raw.strip().lower()


def peek_model_mode() -> str:
    """Return the raw mode token. Unknown values are returned as-is."""

    return raw_model_mode()


def resolve_model_mode() -> ModelMode:
    value = raw_model_mode()
    if value == MODE_FAKE:
        return MODE_FAKE
    if value == MODE_LIVE:
        return MODE_LIVE
    raise ApplicationError("model", "schema_invalid")


def live_test_enabled() -> bool:
    return os.environ.get(ENV_LIVE_TEST) == "1"


def configured_region() -> str:
    return (
        os.environ.get("ITAA_GCP_REGION") or os.environ.get("GOOGLE_CLOUD_LOCATION") or ""
    ).strip()


def uses_vertex() -> bool:
    return os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() == "true"


def vertex_project() -> str:
    return os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()


def vertex_config_ready() -> bool:
    return uses_vertex() and bool(vertex_project()) and bool(configured_region())


def apply_vertex_location() -> None:
    """Copy the documented region into the Vertex location env if unset."""

    region = configured_region()
    if region and not os.environ.get("GOOGLE_CLOUD_LOCATION"):
        os.environ["GOOGLE_CLOUD_LOCATION"] = region
