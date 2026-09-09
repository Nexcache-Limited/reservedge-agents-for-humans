from __future__ import annotations

from fastapi.testclient import TestClient
from wp04_helpers import (
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
from wp06_fakes import build_facade, jfk_payload

from itaa_api.app import create_app
from itaa_domain.value_objects import format_utc

PREFIX = "/v1/simulations/airport-parking"


def _gov(approval_id: object) -> dict[str, object]:
    return {
        "actorId": BUYER.actor_id.to_primitive(),
        "ownerId": OWNER.to_primitive(),
        "approvalId": approval_id.to_primitive(),
        "correlationId": CORRELATION.to_primitive(),
        "issuedAt": format_utc(CREATED_AT),
        "expiresAt": format_utc(EXPIRES_AT),
    }


def test_http_jfk_path_with_fixture_suppliers() -> None:
    client = TestClient(create_app(build_facade()))
    created = client.post(f"{PREFIX}/intents", json=jfk_payload())
    assert created.status_code == 200
    intent_id = created.json()["intentId"]
    assert created.json()["state"] == "AWAITING_REQUIREMENT_CONFIRMATION"
    confirmed = client.post(f"{PREFIX}/intents/{intent_id}/confirm", json=_gov(A1_ID))
    assert confirmed.status_code == 200
    assert confirmed.json()["state"] == "AWAITING_DISPATCH_APPROVAL"
    dispatched = client.post(f"{PREFIX}/intents/{intent_id}/dispatch", json=_gov(A2_ID))
    assert dispatched.status_code == 200
    body = dispatched.json()
    by_id = {item["offerId"]: item for item in body["offers"]}
    sky = by_id["of_01k2m3n4p5q6r7s8t9v0w1x2a2"]
    park = by_id["of_01k2m3n4p5q6r7s8t9v0w1x2a1"]
    flex = by_id["of_01k2m3n4p5q6r7s8t9v0w1x2a3"]
    assert sky["rank"] == 1 and sky["recommended"] is True
    assert park["rank"] == 2
    assert flex["rank"] == 3
    assert sky["price"]["totalMinor"] == 14800
    assert park["price"]["totalMinor"] == 11900
    assert flex["price"]["totalMinor"] == 16900
    for item in (sky, park, flex):
        assert "scoreMicros" not in item
        assert "termsHash" in item
        assert "totalMinor" not in item
    assert body["downside"]["delta"] == 2900
    accepted = client.post(
        f"{PREFIX}/intents/{intent_id}/acceptances",
        json={**_gov(A3_ID), "offerId": body["recommendedOfferId"], "offerVersion": 1},
    )
    assert accepted.status_code == 200
    winner = next(item for item in body["offers"] if item["recommended"])
    authorized = client.post(
        f"{PREFIX}/intents/{intent_id}/transaction-authorizations",
        headers={"Idempotency-Key": "ik_01k2m3n4p5q6r7s8t9v0w1x2c1"},
        json={
            **_gov(A4_ID),
            "acceptanceId": accepted.json()["acceptance"]["acceptanceId"],
            "amountMinor": winner["price"]["totalMinor"],
            "currency": "USD",
            "supplierToken": winner["supplierToken"],
            "action": "reserve_parking",
            "mode": "SIMULATED",
            "idempotencyKey": "ik_01k2m3n4p5q6r7s8t9v0w1x2c1",
        },
    )
    assert authorized.status_code == 200
    assert authorized.json()["transaction"]["mode"] == "SIMULATED"
    snapshot = client.get(f"{PREFIX}/intents/{intent_id}")
    assert snapshot.status_code == 200
    assert "buyerToken" not in snapshot.text
    assert "prompt" not in snapshot.text
