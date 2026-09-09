from __future__ import annotations

from fastapi.testclient import TestClient
from wp06_fakes import build_facade, jfk_payload

from itaa_api.app import create_app
from itaa_api.composition import build_facade as compose_facade

PARKING = "/v1/simulations/airport-parking"
PREFIX = "/v1/orchestration"
BODY = "01k2m3n4p5q6r7s8t9v0w1x2y3"
PI = "pi_" + BODY
OI = "oi_" + BODY
BT = "bt_" + BODY


def test_pi_alias_and_oi_canonical_are_stable() -> None:
    client = TestClient(create_app(build_facade()))
    created = client.post(f"{PARKING}/intents", json=jfk_payload())
    assert created.status_code == 200
    assert created.json()["intentId"] == PI
    via_pi = client.get(f"{PREFIX}/intents/{PI}")
    via_oi = client.get(f"{PREFIX}/intents/{OI}")
    assert via_pi.status_code == 200
    assert via_oi.status_code == 200
    assert via_pi.json() == via_oi.json()
    assert via_pi.json()["intentId"] == OI
    assert via_pi.json()["planId"] == "pl_" + BODY
    assert via_pi.json()["ledgerId"] == "ld_" + BODY
    task = client.get(f"{PREFIX}/intents/{PI}/tasks/{BT}")
    assert task.status_code == 200
    assert task.json()["taskId"] == BT
    assert task.json()["purchaseIntentId"] == PI


def test_malformed_ids_are_invalid_opaque_syntax() -> None:
    client = TestClient(create_app(build_facade()))
    client.post(f"{PARKING}/intents", json=jfk_payload())
    bad_intent = client.get(f"{PREFIX}/intents/not-an-id")
    assert bad_intent.status_code == 400
    assert bad_intent.json()["error"]["field"] == "intentId"
    assert bad_intent.json()["error"]["code"] == "invalid_opaque_syntax"
    bad_task = client.get(f"{PREFIX}/intents/{PI}/tasks/not-a-task")
    assert bad_task.status_code == 400
    assert bad_task.json()["error"]["field"] == "taskId"
    assert bad_task.json()["error"]["code"] == "invalid_opaque_syntax"


def test_unknown_and_restart_are_unknown_resource() -> None:
    empty = TestClient(create_app(build_facade()))
    missing = empty.get(f"{PREFIX}/intents/{PI}")
    assert missing.status_code == 404
    assert missing.json()["error"]["field"] == "intentId"
    assert missing.json()["error"]["code"] == "unknown_resource"
    primed = TestClient(create_app(build_facade()))
    created = primed.post(f"{PARKING}/intents", json=jfk_payload())
    assert created.status_code == 200
    assert primed.get(f"{PREFIX}/intents/{OI}").status_code == 200
    restarted = TestClient(create_app(build_facade()))
    after_restart = restarted.get(f"{PREFIX}/intents/{OI}")
    assert after_restart.status_code == 404
    assert after_restart.json()["error"]["code"] == "unknown_resource"
    composed = TestClient(create_app(compose_facade()))
    assert composed.get(f"{PREFIX}/intents/{PI}").status_code == 404


def test_parking_intent_id_stays_pi() -> None:
    client = TestClient(create_app(build_facade()))
    created = client.post(f"{PARKING}/intents", json=jfk_payload())
    assert created.json()["intentId"] == PI
    snapshot = client.get(f"{PARKING}/intents/{PI}")
    assert snapshot.status_code == 200
    assert snapshot.json()["intentId"] == PI
    orchestration = client.get(f"{PREFIX}/intents/{PI}")
    assert orchestration.json()["intentId"] == OI
