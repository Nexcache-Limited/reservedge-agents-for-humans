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
KEY = "ik_01k2m3n4p5q6r7s8t9v0w1x2c1"
OTHER = "ik_01k2m3n4p5q6r7s8t9v0w1x2c2"


def _gov(approval_id: object) -> dict[str, object]:
    return {
        "actorId": BUYER.actor_id.to_primitive(),
        "ownerId": OWNER.to_primitive(),
        "approvalId": approval_id.to_primitive(),
        "correlationId": CORRELATION.to_primitive(),
        "issuedAt": format_utc(CREATED_AT),
        "expiresAt": format_utc(EXPIRES_AT),
    }


def _ready_authorization() -> tuple[TestClient, str, dict[str, object]]:
    client = TestClient(create_app(build_facade()))
    created = client.post(f"{PREFIX}/intents", json=jfk_payload())
    intent_id = created.json()["intentId"]
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
        "idempotencyKey": KEY,
    }
    return client, intent_id, payload


def test_matching_header_and_body_replay_same_result_ref() -> None:
    client, intent_id, payload = _ready_authorization()
    first = client.post(
        f"{PREFIX}/intents/{intent_id}/transaction-authorizations",
        headers={"Idempotency-Key": KEY},
        json=payload,
    )
    replay = client.post(
        f"{PREFIX}/intents/{intent_id}/transaction-authorizations",
        headers={"Idempotency-Key": KEY},
        json=payload,
    )
    assert first.status_code == 200
    assert replay.status_code == 200
    assert first.json()["transaction"]["resultRef"] == replay.json()["transaction"]["resultRef"]
    assert KEY not in first.text


def test_missing_idempotency_header_is_closed() -> None:
    client, intent_id, payload = _ready_authorization()
    response = client.post(
        f"{PREFIX}/intents/{intent_id}/transaction-authorizations",
        json=payload,
    )
    assert response.status_code == 400
    body = response.json()["error"]
    assert set(body) == {"code", "field", "correlationId"}
    assert body["code"] in {"schema_invalid", "required"}
    assert KEY not in response.text
    assert OTHER not in response.text


def test_mismatched_header_and_body_is_closed() -> None:
    client, intent_id, payload = _ready_authorization()
    response = client.post(
        f"{PREFIX}/intents/{intent_id}/transaction-authorizations",
        headers={"Idempotency-Key": OTHER},
        json=payload,
    )
    assert response.status_code == 400
    body = response.json()["error"]
    assert body["code"] == "mismatch"
    assert body["field"] == "idempotencyKey"
    assert KEY not in response.text
    assert OTHER not in response.text
    snapshot = client.get(f"{PREFIX}/intents/{intent_id}")
    assert snapshot.json()["state"] == "ACCEPTANCE_RECORDED"
    assert snapshot.json()["transaction"] is None
