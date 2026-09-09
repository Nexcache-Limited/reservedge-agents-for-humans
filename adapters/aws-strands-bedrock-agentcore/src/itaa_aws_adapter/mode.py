"""Explicit AWS model-mode selection. Does not import Strands or boto3."""

from __future__ import annotations

import os
from typing import Literal

from itaa_application.errors import ApplicationError
from itaa_aws_adapter import DEFAULT_LIVE_MODEL

ModelMode = Literal["fake", "live"]

ENV_MODEL_MODE = "ITAA_AWS_MODEL_MODE"
ENV_LIVE_ALIAS = "ITAA_AWS_LIVE"
ENV_LIVE_TEST = "ITAA_AWS_LIVE_TEST"
ENV_LIVE_INVOKE = "ITAA_AWS_LIVE_INVOKE"
ENV_TIMEOUT_MS = "ITAA_AWS_TIMEOUT_MS"
LIVE_SOURCE_REGION = "eu-west-2"
ENV_MODEL = "ITAA_AWS_MODEL"
ENV_ADAPTER_URL = "ITAA_AWS_ADAPTER_URL"
MODE_FAKE: ModelMode = "fake"
MODE_LIVE: ModelMode = "live"
CLOSED_MODES: frozenset[str] = frozenset({MODE_FAKE, MODE_LIVE})
ALLOWED_LIVE_MODELS: frozenset[str] = frozenset({DEFAULT_LIVE_MODEL})
TIMEOUT_MIN_MS = 5000
TIMEOUT_MAX_MS = 45000
DEFAULT_ADAPTER_URL = "http://127.0.0.1:8080"


def raw_model_mode() -> str:
    raw = os.environ.get(ENV_MODEL_MODE)
    if raw is None or raw.strip() == "":
        if os.environ.get(ENV_LIVE_ALIAS) == "1":
            return MODE_LIVE
        return MODE_FAKE
    return raw.strip().lower()


def peek_model_mode() -> str:
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


def live_invoke_authorized() -> bool:
    """Fail-closed until live invoke is authorized for local UAT."""
    return os.environ.get(ENV_LIVE_INVOKE) == "1"


def configured_model_id() -> str:
    raw = os.environ.get(ENV_MODEL)
    if raw is None or raw.strip() == "":
        return DEFAULT_LIVE_MODEL
    return raw.strip()


def resolve_live_model_id() -> str:
    model_id = configured_model_id()
    if model_id not in ALLOWED_LIVE_MODELS:
        raise ApplicationError("model", "schema_invalid")
    return model_id


def resolve_timeout_ms() -> int:
    raw = os.environ.get(ENV_TIMEOUT_MS)
    if raw is None or raw.strip() == "":
        raise ApplicationError("model", "schema_invalid")
    try:
        value = int(raw.strip())
    except ValueError:
        raise ApplicationError("model", "schema_invalid") from None
    if value < TIMEOUT_MIN_MS or value > TIMEOUT_MAX_MS:
        raise ApplicationError("model", "schema_invalid")
    return value


def adapter_base_url() -> str:
    raw = os.environ.get(ENV_ADAPTER_URL)
    if raw is None or raw.strip() == "":
        return DEFAULT_ADAPTER_URL
    return raw.strip().rstrip("/")
