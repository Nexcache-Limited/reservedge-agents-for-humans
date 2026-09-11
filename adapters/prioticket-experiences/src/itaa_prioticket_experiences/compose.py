"""Compose the competition experience-search port. CI/default remains credential-free."""

from __future__ import annotations

from itaa_application.external_search_port import ExperienceSearchPort
from itaa_prioticket_experiences.adapter import (
    PrioticketExperienceAdapter,
    experience_search_mode,
    prioticket_client_id,
    prioticket_client_secret,
)
from itaa_prioticket_experiences.fake import FakeExperienceSearchAdapter

ENV_MODE = "ITAA_EXPERIENCE_SEARCH_MODE"
ENV_CLIENT_ID = "ITAA_PRIOTICKET_CLIENT_ID"
ENV_CLIENT_SECRET = "ITAA_PRIOTICKET_CLIENT_SECRET"
ENV_TIMEOUT_MS = "ITAA_PRIOTICKET_TIMEOUT_MS"
ENV_BASE_URL = "ITAA_PRIOTICKET_BASE_URL"


def compose_experience_search_port() -> ExperienceSearchPort:
    if (
        experience_search_mode() == "sandbox"
        and prioticket_client_id()
        and prioticket_client_secret()
    ):
        return PrioticketExperienceAdapter.from_env()
    return FakeExperienceSearchAdapter()
