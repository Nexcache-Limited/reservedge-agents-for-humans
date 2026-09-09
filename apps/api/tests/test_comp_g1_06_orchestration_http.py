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
from itaa_api.composition import build_facade as compose_facade
from itaa_domain.value_objects import format_utc

PARKING = "/v1/simulations/airport-parking"
PREFIX = "/v1/orchestration"
BODY = "01k2m3n4p5q6r7s8t9v0w1x2y3"
PI = "pi_" + BODY
OI = "oi_" + BODY
BT = "bt_" + BODY


def _gov(approval_id: object) -> dict[str, object]:
    return {
        "actorId": BUYER.actor_id.to_primitive(),
        "ownerId": OWNER.to_primitive(),
        "approvalId": approval_id.to_primitive(),
        "correlationId": CORRELATION.to_primitive(),
        "issuedAt": format_utc(CREATED_AT),
        "expiresAt": format_utc(EXPIRES_AT),
    }


def _client() -> TestClient:
    return TestClient(create_app(build_facade()))


def _walk(client: TestClient, *, through: str) -> str:
    created = client.post(f"{PARKING}/intents", json=jfk_payload())
    assert created.status_code == 200
    intent_id = created.json()["intentId"]
    if through == "created":
        return intent_id
    confirmed = client.post(f"{PARKING}/intents/{intent_id}/confirm", json=_gov(A1_ID))
    assert confirmed.status_code == 200
    if through == "confirmed":
        return intent_id
    dispatched = client.post(f"{PARKING}/intents/{intent_id}/dispatch", json=_gov(A2_ID))
    assert dispatched.status_code == 200
    if through == "dispatched":
        return intent_id
    winner = next(item for item in dispatched.json()["offers"] if item["recommended"])
    accepted = client.post(
        f"{PARKING}/intents/{intent_id}/acceptances",
        json={**_gov(A3_ID), "offerId": winner["offerId"], "offerVersion": 1},
    )
    assert accepted.status_code == 200
    if through == "accepted":
        return intent_id
    authorized = client.post(
        f"{PARKING}/intents/{intent_id}/transaction-authorizations",
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
    return intent_id


def test_orchestration_reads_follow_the_parking_path() -> None:
    client = _client()
    _walk(client, through="created")
    created = client.get(f"{PREFIX}/intents/{PI}")
    assert created.status_code == 200
    assert created.json()["state"] == "attention"
    assert created.json()["intentId"] == OI
    assert created.json()["objective"] == "Airport parking JFK"
    assert created.json()["simulation"] is True
    assert created.json()["durability"] == "unsupported"
    assert "conversationId" not in created.json()
    client = _client()
    _walk(client, through="confirmed")
    assert client.get(f"{PREFIX}/intents/{PI}").json()["state"] == "attention"
    client = _client()
    _walk(client, through="dispatched")
    assert client.get(f"{PREFIX}/intents/{PI}").json()["state"] == "offers_ready"
    plan = client.get(f"{PREFIX}/intents/{PI}/plan")
    assert plan.status_code == 200
    assert plan.json()["taskIds"] == [BT]
    task = client.get(f"{PREFIX}/intents/{PI}/tasks/{BT}")
    assert task.status_code == 200
    assert task.json()["state"] == "offers_ready"
    assert task.json()["domain"] == "parking"
    assert task.json()["inventory"] == "not_held"
    ledger = client.get(f"{PREFIX}/intents/{PI}/ledger")
    assert ledger.status_code == 200
    assert ledger.json()["rows"][0]["estimatedMinor"] == 14800
    assert ledger.json()["rows"][0]["confirmedBookingMinor"] == 0
    client = _client()
    _walk(client, through="accepted")
    assert client.get(f"{PREFIX}/intents/{PI}").json()["state"] == "attention"
    assert client.get(f"{PREFIX}/intents/{PI}/tasks/{BT}").json()["state"] == "a4_required"
    client = _client()
    _walk(client, through="authorized")
    parent = client.get(f"{PREFIX}/intents/{OI}")
    assert parent.json()["state"] == "completed_simulated"
    task = client.get(f"{PREFIX}/intents/{OI}/tasks/{BT}")
    assert task.json()["state"] == "authorized_simulated"
    assert task.json()["transactionResult"] == "authorized_simulated"
    ledger = client.get(f"{PREFIX}/intents/{OI}/ledger")
    assert ledger.json()["rows"][0]["authorizedSimulatedMinor"] == 14800
    assert ledger.json()["rows"][0]["confirmedBookingMinor"] == 0
    assert ledger.json()["rows"][0]["authorizedLiveMinor"] == 0
    assert ledger.json()["rows"][0]["payableNowMinor"] == 0
    assert "fx" not in ledger.json()
    for document in (parent.json(), task.json(), ledger.json()):
        assert "scoreMicros" not in document


def test_idempotent_reads_and_no_score_micros_on_json() -> None:
    client = _client()
    _walk(client, through="dispatched")
    first = client.get(f"{PREFIX}/intents/{PI}")
    second = client.get(f"{PREFIX}/intents/{PI}")
    assert first.status_code == 200
    assert first.json() == second.json()
    assert "scoreMicros" not in first.text
    plan_a = client.get(f"{PREFIX}/intents/{PI}/plan")
    plan_b = client.get(f"{PREFIX}/intents/{PI}/plan")
    assert plan_a.json() == plan_b.json()
    assert plan_a.json()["combinedRecommendationsEligible"] is False


def test_task_not_on_intent_is_unknown_resource() -> None:
    client = _client()
    _walk(client, through="created")
    response = client.get(f"{PREFIX}/intents/{PI}/tasks/bt_01k2m3n4p5q6r7s8t9v0w1x2zz")
    assert response.status_code == 404
    assert response.json()["error"]["field"] == "taskId"
    assert response.json()["error"]["code"] == "unknown_resource"


def test_composition_facade_also_serves_orchestration() -> None:
    client = TestClient(create_app(compose_facade()))
    created = client.post(f"{PARKING}/intents", json=jfk_payload())
    assert created.status_code == 200
    intent_id = created.json()["intentId"]
    response = client.get(f"{PREFIX}/intents/{intent_id}")
    assert response.status_code == 200
    assert response.json()["durability"] == "unsupported"
    assert response.json()["state"] == "attention"


def test_parking_golden_path_still_works() -> None:
    client = TestClient(create_app(build_facade()))
    created = client.post(f"{PARKING}/intents", json=jfk_payload())
    assert created.status_code == 200
    intent_id = created.json()["intentId"]
    assert created.json()["state"] == "AWAITING_REQUIREMENT_CONFIRMATION"
    confirmed = client.post(f"{PARKING}/intents/{intent_id}/confirm", json=_gov(A1_ID))
    assert confirmed.status_code == 200
    dispatched = client.post(f"{PARKING}/intents/{intent_id}/dispatch", json=_gov(A2_ID))
    assert dispatched.status_code == 200
    assert "scoreMicros" not in dispatched.text
    winner = next(item for item in dispatched.json()["offers"] if item["recommended"])
    accepted = client.post(
        f"{PARKING}/intents/{intent_id}/acceptances",
        json={**_gov(A3_ID), "offerId": winner["offerId"], "offerVersion": 1},
    )
    assert accepted.status_code == 200
    authorized = client.post(
        f"{PARKING}/intents/{intent_id}/transaction-authorizations",
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
    snapshot = client.get(f"{PARKING}/intents/{intent_id}")
    assert snapshot.status_code == 200
    assert snapshot.json()["state"] == "TRANSACTION_AUTHORIZED_SIMULATED"
