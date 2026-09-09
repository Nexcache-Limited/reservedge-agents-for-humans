from __future__ import annotations

from fastapi.testclient import TestClient
from wp06_fakes import build_facade, jfk_payload  # type: ignore[import-not-found]

from itaa_api.app import create_app

PREFIX = "/v1/simulations/airport-parking"
FORBIDDEN = (
    "buyerToken",
    "approvedPayloadHash",
    "prompt",
    "chain",
    "traceback",
    "password",
    "authorization internals",
)


def test_snapshots_omit_identity_and_policy_internals() -> None:
    client = TestClient(create_app(build_facade()))
    created = client.post(f"{PREFIX}/intents", json=jfk_payload())
    text = created.text
    for needle in FORBIDDEN:
        assert needle not in text
    assert created.json()["simulation"] is True
