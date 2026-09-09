from __future__ import annotations

from fastapi.testclient import TestClient
from wp04_helpers import (  # type: ignore[import-not-found]
    A1_ID,
    A2_ID,
    A3_ID,
    A4_ID,
    BUYER,
    CORRELATION,
    CREATED_AT,
    EXPIRES_AT,
    OWNER,
)
from wp06_fakes import build_facade, jfk_payload  # type: ignore[import-not-found]

from itaa_api.app import create_app
from itaa_domain.identifiers import ApprovalId
from itaa_domain.value_objects import format_utc

PREFIX = "/v1/simulations/airport-parking"


def _gov(approval_id: ApprovalId) -> dict[str, object]:
    return {
        "actorId": BUYER.actor_id.to_primitive(),
        "ownerId": OWNER.to_primitive(),
        "approvalId": approval_id.to_primitive(),
        "correlationId": CORRELATION.to_primitive(),
        "issuedAt": format_utc(CREATED_AT),
        "expiresAt": format_utc(EXPIRES_AT),
    }


def test_duplicate_intent_conflicts_and_conflicting_auth_fails() -> None:
    client = TestClient(create_app(build_facade()))
    first = client.post(f"{PREFIX}/intents", json=jfk_payload())
    second = client.post(f"{PREFIX}/intents", json=jfk_payload())
    assert first.status_code == 200
    assert second.status_code == 409
    intent_id = first.json()["intentId"]
    client.post(f"{PREFIX}/intents/{intent_id}/confirm", json=_gov(A1_ID))
    dispatched = client.post(f"{PREFIX}/intents/{intent_id}/dispatch", json=_gov(A2_ID))
    winner = next(item for item in dispatched.json()["offers"] if item["recommended"])
    accepted = client.post(
        f"{PREFIX}/intents/{intent_id}/acceptances",
        json={**_gov(A3_ID), "offerId": winner["offerId"], "offerVersion": 1},
    )
    payload = {
        **_gov(A4_ID),
        "acceptanceId": accepted.json()["acceptance"]["acceptanceId"],
        "amountMinor": winner["price"]["totalMinor"],
        "currency": "USD",
        "supplierToken": winner["supplierToken"],
        "action": "reserve_parking",
        "mode": "SIMULATED",
        "idempotencyKey": "ik_01k2m3n4p5q6r7s8t9v0w1x2c1",
    }
    ok = client.post(
        f"{PREFIX}/intents/{intent_id}/transaction-authorizations",
        headers={"Idempotency-Key": "ik_01k2m3n4p5q6r7s8t9v0w1x2c1"},
        json=payload,
    )
    conflict = client.post(
        f"{PREFIX}/intents/{intent_id}/transaction-authorizations",
        headers={"Idempotency-Key": "ik_01k2m3n4p5q6r7s8t9v0w1x2c1"},
        json={**payload, "amountMinor": winner["price"]["totalMinor"] + 100},
    )
    assert ok.status_code == 200
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "request_mismatch"
