"""Competition LiteAPI stay-search adapter. Not production provider architecture."""

from __future__ import annotations

from itaa_liteapi_hotels.compose import (
    ENV_API_KEY,
    ENV_LIVE_TEST,
    ENV_MODE,
    ENV_TIMEOUT_MS,
    compose_stay_search_port,
)

ADAPTER_VERSION = "0.1.0"
PROVIDER_ID = "liteapi"

__all__ = [
    "ADAPTER_VERSION",
    "ENV_API_KEY",
    "ENV_LIVE_TEST",
    "ENV_MODE",
    "ENV_TIMEOUT_MS",
    "PROVIDER_ID",
    "compose_stay_search_port",
]
