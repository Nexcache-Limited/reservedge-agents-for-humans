from __future__ import annotations

from fastapi.testclient import TestClient
from wp04_helpers import A1_ID, A2_ID, BUYER, CORRELATION, CREATED_AT, EXPIRES_AT, OWNER
from wp06_fakes import jfk_payload

from itaa_api.app import create_app
from itaa_api.composition import build_facade
from itaa_domain.value_objects import format_utc

PREFIX = "/v1/simulations/airport-parking"


def test_healthz_and_readyz_are_local_and_closed() -> None:
    client = TestClient(create_app())
    live = client.get("/healthz")
    ready = client.get("/readyz")
    assert live.status_code == 200
    assert ready.status_code == 200
    assert live.json() == {"status": "ok", "environment": "local_simulation"}
    assert ready.json() == {
        "status": "ready",
        "environment": "local_simulation",
        "durability": "unsupported",
    }
    dumped = live.text + ready.text
    assert "secret" not in dumped
    assert "postgres" not in dumped
    assert "token" not in dumped


def test_unknown_route_is_redacted() -> None:
    client = TestClient(create_app())
    response = client.get("/admin/debug")
    assert response.status_code == 404
    body = response.json()
    assert set(body["error"]) == {"code", "field", "correlationId"}
    assert "admin" not in str(body)
    assert "traceback" not in response.text.lower()


def test_default_composition_can_create_and_dispatch() -> None:
    client = TestClient(create_app(build_facade()))
    created = client.post(f"{PREFIX}/intents", json=jfk_payload())
    assert created.status_code == 200
    intent_id = created.json()["intentId"]
    governance = {
        "actorId": BUYER.actor_id.to_primitive(),
        "ownerId": OWNER.to_primitive(),
        "approvalId": A1_ID.to_primitive(),
        "correlationId": CORRELATION.to_primitive(),
        "issuedAt": format_utc(CREATED_AT),
        "expiresAt": format_utc(EXPIRES_AT),
    }
    confirmed = client.post(f"{PREFIX}/intents/{intent_id}/confirm", json=governance)
    assert confirmed.status_code == 200
    dispatched = client.post(
        f"{PREFIX}/intents/{intent_id}/dispatch",
        json={**governance, "approvalId": A2_ID.to_primitive()},
    )
    assert dispatched.status_code == 200
    assert len(dispatched.json()["supplierOutcomes"]) == 3
    assert dispatched.json()["simulation"] is True
