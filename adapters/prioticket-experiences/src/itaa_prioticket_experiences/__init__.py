"""Competition Prioticket experience-search adapter. Not production provider architecture."""

from __future__ import annotations

from itaa_prioticket_experiences.compose import (
    ENV_BASE_URL,
    ENV_CLIENT_ID,
    ENV_CLIENT_SECRET,
    ENV_MODE,
    ENV_TIMEOUT_MS,
    compose_experience_search_port,
)

ADAPTER_VERSION = "0.1.0"
PROVIDER_ID = "prioticket"

__all__ = [
    "ADAPTER_VERSION",
    "ENV_BASE_URL",
    "ENV_CLIENT_ID",
    "ENV_CLIENT_SECRET",
    "ENV_MODE",
    "ENV_TIMEOUT_MS",
    "PROVIDER_ID",
    "compose_experience_search_port",
]
