"""COMP-G1-04 buyer-scoped portfolio HTTP: cookie isolation, list, lifecycle."""

from __future__ import annotations

from fastapi.testclient import TestClient

from itaa_api.app import create_app
from itaa_api.composition import build_facade
from itaa_api.intake import PREFIX, build_intake_app
from itaa_api.portfolio_http import COOKIE_NAME
from itaa_application.golden_path import GoldenPathFacade

JFK_TEXT = (
    "I'm flying from JFK on September 3 at 1 PM and returning September 8 at 10 PM. "
    "I have a standard EV, prefer covered parking, and don't want a shuttle longer than 20 minutes."
)
CONFIRMED = {
    "airportCode": "JFK",
    "start": "2026-09-03T13:00:00Z",
    "end": "2026-09-08T22:00:00Z",
    "vehicleClass": "standard",
    "covered": "preferred",
    "shuttleMaxMinutes": 20,
    "currency": "USD",
    "accessibility": ["ev_charging"],
}
REPLACE_KEY = "ik_01k2m3n4p5q6r7s8t9v0w1x2k1"
REPLACE_KEY_B = "ik_01k2m3n4p5q6r7s8t9v0w1x2k2"


def _happy_extract(payload: dict[str, object]) -> dict[str, object]:
    return {
        "proposal": {
            "category": "airport_parking",
            "location": {"airportCode": "JFK"},
            "serviceWindow": {
                "start": "2026-09-03T13:00:00Z",
                "end": "2026-09-08T22:00:00Z",
            },
            "requirements": {
                "vehicleClass": "standard",
                "covered": "preferred",
                "shuttleMaxMinutes": 20,
            },
            "constraints": {"currency": "USD", "accessibility": ["ev_charging"]},
        },
        "fieldConfidence": {},
        "missingFields": [],
        "ambiguousFields": [],
        "evidenceSpans": [],
        "correlationId": payload["correlationId"],
    }


def _clients(
    facade: GoldenPathFacade | None = None,
) -> tuple[TestClient, TestClient, GoldenPathFacade]:
    chosen = facade or build_facade()
    application = create_app(chosen)
    application.state.extract_client = _happy_extract
    return TestClient(application), TestClient(application), chosen


def _create(client: TestClient) -> str:
    extracted = client.post(
        f"{PREFIX}/intake/extractions",
        json={"text": JFK_TEXT, "category": "airport_parking"},
    )
    assert extracted.status_code == 200, extracted.text
    created = client.post(
        f"{PREFIX}/intake/intents",
        json={"intakeId": extracted.json()["intakeId"], **CONFIRMED},
    )
    assert created.status_code == 200, created.text
    return str(created.json()["intentId"])


def test_portfolio_cookie_is_httponly_and_not_in_javascript_body() -> None:
    client, _other, _facade = _clients()
    extracted = client.post(
        f"{PREFIX}/intake/extractions",
        json={"text": JFK_TEXT, "category": "airport_parking"},
    )
    assert extracted.status_code == 200
    cookie = extracted.cookies.get(COOKIE_NAME)
    assert cookie is not None
    assert cookie.startswith("pf_")
    header = extracted.headers.get("set-cookie", "").lower()
    assert "httponly" in header
    assert "samesite=lax" in header
    assert cookie not in extracted.text


def test_foreign_portfolio_cannot_list_or_mutate() -> None:
    alice, bob, _facade = _clients()
    intent_id = _create(alice)
    listed = bob.get(f"{PREFIX}/intake/intents")
    assert listed.status_code == 200
    body = listed.json()
    assert body["needsYou"] == []
    assert body["running"] == []
    assert body["saved"] == []
    assert body["history"] == []
    cancel = bob.post(f"{PREFIX}/intake/intents/{intent_id}/cancel", json={})
    assert cancel.status_code == 404
    error = cancel.json()["error"]
    assert error["code"] == "unknown_resource"
    assert error["field"] == "intentId"
    assert intent_id not in cancel.text
    assert "pf_" not in cancel.text
    own = alice.get(f"{PREFIX}/intake/intents")
    assert any(item["intentId"] == intent_id for item in own.json()["needsYou"])


def test_list_is_deterministic_and_save_is_presentation_only() -> None:
    client, _bob, _facade = _clients()
    first = _create(client)
    second = _create(client)
    listed = client.get(f"{PREFIX}/intake/intents")
    assert listed.status_code == 200
    needs = listed.json()["needsYou"]
    assert {item["intentId"] for item in needs} == {first, second}
    saved = client.post(f"{PREFIX}/intake/intents/{first}/save", json={})
    assert saved.status_code == 200
    assert saved.json()["saved"] is True
    assert saved.json()["state"] == "AWAITING_REQUIREMENT_CONFIRMATION"
    after = client.get(f"{PREFIX}/intake/intents")
    assert [item["intentId"] for item in after.json()["saved"]] == [first]
    assert [item["intentId"] for item in after.json()["needsYou"]] == [second]


def test_cancel_replace_delete_and_activity() -> None:
    client, _bob, _facade = _clients()
    draft = _create(client)
    deleted = client.delete(f"{PREFIX}/intake/intents/{draft}")
    assert deleted.status_code == 200
    gone = client.get(f"{PREFIX}/intake/intents")
    assert gone.json()["needsYou"] == []

    intent_id = _create(client)
    confirmed = client.post(f"{PREFIX}/intake/intents/{intent_id}/confirm", json={})
    assert confirmed.status_code == 200
    refused = client.delete(f"{PREFIX}/intake/intents/{intent_id}")
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "conflict"

    cancelled = client.post(f"{PREFIX}/intake/intents/{intent_id}/cancel", json={})
    assert cancelled.status_code == 200
    assert cancelled.json()["state"] == "CANCELLED"
    history = client.get(f"{PREFIX}/intake/intents")
    assert history.json()["history"][0]["state"] == "CANCELLED"

    original = _create(client)
    replaced = client.post(
        f"{PREFIX}/intake/intents/{original}/replace",
        headers={"Idempotency-Key": REPLACE_KEY},
        json={},
    )
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["previous"]["state"] == "CANCELLED"
    draft_id = replaced.json()["draft"]["intentId"]
    replay = client.post(
        f"{PREFIX}/intake/intents/{original}/replace",
        headers={"Idempotency-Key": REPLACE_KEY},
        json={},
    )
    assert replay.json()["draft"]["intentId"] == draft_id
    conflict = client.post(
        f"{PREFIX}/intake/intents/{original}/replace",
        headers={"Idempotency-Key": REPLACE_KEY_B},
        json={},
    )
    assert conflict.status_code == 409
    activity = client.get(f"{PREFIX}/intake/intents/{draft_id}/activity")
    assert activity.status_code == 200
    labels = [item["label"] for item in activity.json()["activity"]]
    assert "Request created" in labels
    assert all("A1" not in label and "Gate" not in label for label in labels)


def test_openapi_includes_portfolio_paths() -> None:
    document = create_app().openapi()
    paths = document["paths"]
    assert f"{PREFIX}/intake/intents" in paths
    assert "get" in paths[f"{PREFIX}/intake/intents"]
    assert f"{PREFIX}/intake/intents/{{intent_id}}/cancel" in paths
    assert f"{PREFIX}/intake/intents/{{intent_id}}/replace" in paths
    assert f"{PREFIX}/intake/intents/{{intent_id}}/save" in paths
    assert f"{PREFIX}/intake/intents/{{intent_id}}/activity" in paths


def test_build_intake_app_also_sets_portfolio_cookie() -> None:
    client = TestClient(build_intake_app(build_facade(), extract_client=_happy_extract))
    intent_id = _create(client)
    listed = client.get(f"{PREFIX}/intake/intents")
    assert listed.status_code == 200
    assert listed.json()["needsYou"][0]["intentId"] == intent_id
