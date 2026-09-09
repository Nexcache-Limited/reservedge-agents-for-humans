"""COMP-G1-02 intake extract + confirmed fields + A1–A4."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient

from itaa_api.composition import build_facade
from itaa_api.intake import PREFIX, build_intake_app
from itaa_application.errors import ApplicationError
from itaa_application.supplier_port import WallClock
from itaa_domain.value_objects import parse_utc
from itaa_google_adapter.agent import compose_agent
from itaa_google_adapter.ports import ExtractionRequest

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


def _happy_extract(payload: dict[str, object]) -> dict[str, object]:
    assert payload["category"] == "airport_parking"
    assert isinstance(payload["correlationId"], str)
    assert str(payload["correlationId"]).startswith("cr_")
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
        "fieldConfidence": {
            "location.airportCode": 0.91,
            "serviceWindow.start": 0.88,
            "serviceWindow.end": 0.87,
        },
        "missingFields": [],
        "ambiguousFields": [],
        "evidenceSpans": [{"field": "location.airportCode", "start": 16, "end": 19}],
        "fieldAttributions": [
            {"field": "location.airportCode", "origin": "extracted", "confidence": 0.91}
        ],
        "requiresA1": True,
        "accepted": False,
        "fallback": None,
        "rejectionCode": None,
        "correlationId": payload["correlationId"],
    }


def _client(
    extract: Any = _happy_extract,
    facade: Any = None,
) -> TestClient:
    return TestClient(build_intake_app(facade or build_facade(), extract_client=extract))


def _extract_and_confirm(
    client: TestClient,
    confirmed: dict[str, object] | None = None,
    text: str = JFK_TEXT,
) -> tuple[str, dict[str, object]]:
    extracted = client.post(
        f"{PREFIX}/intake/extractions",
        json={"text": text, "category": "airport_parking"},
    )
    assert extracted.status_code == 200, extracted.text
    body = {**(confirmed or CONFIRMED), "intakeId": extracted.json()["intakeId"]}
    created = client.post(f"{PREFIX}/intake/intents", json=body)
    assert created.status_code == 200, created.text
    return created.json()["intentId"], created.json()


def _complete_through_a2(client: TestClient) -> tuple[str, dict[str, object]]:
    intent_id, _ = _extract_and_confirm(client)
    confirmed = client.post(f"{PREFIX}/intake/intents/{intent_id}/confirm", json={})
    assert confirmed.status_code == 200, confirmed.text
    dispatched = client.post(
        f"{PREFIX}/intake/intents/{intent_id}/dispatch", json={"confirm": True}
    )
    assert dispatched.status_code == 200, dispatched.text
    return intent_id, dispatched.json()


def test_happy_extract_confirm_and_a1_to_a4() -> None:
    captured: list[dict[str, object]] = []

    def extract(payload: dict[str, object]) -> dict[str, object]:
        captured.append(payload)
        return _happy_extract(payload)

    client = _client(extract)
    extracted = client.post(
        f"{PREFIX}/intake/extractions",
        json={"text": JFK_TEXT, "category": "airport_parking"},
    )
    assert extracted.status_code == 200
    body = extracted.json()
    assert body["intakeId"].startswith("in_")
    assert body["proposal"]["location"]["airportCode"] == "JFK"
    assert body["missingFields"] == []
    assert captured[0]["text"] == JFK_TEXT

    created = client.post(
        f"{PREFIX}/intake/intents",
        json={"intakeId": body["intakeId"], **CONFIRMED},
    )
    assert created.status_code == 200, created.text
    intent_id = created.json()["intentId"]
    assert intent_id.startswith("pi_")
    assert created.json()["state"] == "AWAITING_REQUIREMENT_CONFIRMATION"
    assert created.json()["airport"] == "JFK"
    created_at = parse_utc(created.json()["createdAt"], "createdAt")
    expires_at = parse_utc(created.json()["expiresAt"], "expiresAt")
    assert expires_at - created_at == timedelta(hours=48)
    assert expires_at > created_at

    a1 = client.post(f"{PREFIX}/intake/intents/{intent_id}/confirm", json={})
    assert a1.status_code == 200
    assert a1.json()["state"] == "AWAITING_DISPATCH_APPROVAL"

    a2 = client.post(f"{PREFIX}/intake/intents/{intent_id}/dispatch", json={})
    assert a2.status_code == 200
    assert a2.json()["state"] == "OFFERS_RANKED"
    ranked = a2.json()["offers"]
    by_rank = {item["rank"]: item for item in ranked}
    assert set(by_rank) == {1, 2, 3}
    assert by_rank[1]["price"]["totalMinor"] == 14800
    assert by_rank[2]["price"]["totalMinor"] == 11900
    assert by_rank[3]["price"]["totalMinor"] == 16900
    recommended = a2.json()["recommendedOfferId"]
    winner = next(item for item in ranked if item["offerId"] == recommended)
    assert winner["rank"] == 1
    assert "scoreMicros" not in winner
    assert "termsHash" in winner
    assert winner["price"]["totalMinor"] == 14800
    downside = a2.json()["downside"]
    assert downside["delta"] == 2900

    a3 = client.post(
        f"{PREFIX}/intake/intents/{intent_id}/acceptances",
        json={"offerId": recommended},
    )
    assert a3.status_code == 200, a3.text
    assert a3.json()["state"] == "ACCEPTANCE_RECORDED"

    key = "ik_01k2m3n4p5q6r7s8t9v0w1x2c1"
    a4 = client.post(
        f"{PREFIX}/intake/intents/{intent_id}/transaction-authorizations",
        headers={"Idempotency-Key": key},
        json={
            "acceptanceId": a3.json()["acceptance"]["acceptanceId"],
            "amountMinor": winner["price"]["totalMinor"],
            "currency": winner["price"]["currency"],
            "supplierToken": winner["supplierToken"],
        },
    )
    assert a4.status_code == 200, a4.text
    assert a4.json()["state"] == "TRANSACTION_AUTHORIZED_SIMULATED"
    assert a4.json()["transaction"]["mode"] == "SIMULATED"


def test_missing_end_is_closed() -> None:
    client = _client()
    extracted = client.post(
        f"{PREFIX}/intake/extractions",
        json={"text": JFK_TEXT, "category": "airport_parking"},
    )
    payload = {"intakeId": extracted.json()["intakeId"], **CONFIRMED}
    del payload["end"]
    response = client.post(f"{PREFIX}/intake/intents", json=payload)
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "schema_invalid"
    assert JFK_TEXT not in response.text
    assert "2026-09-03" not in response.text
    assert "JFK" not in response.text


def test_ambiguous_airport_from_extract_client() -> None:
    def extract(payload: dict[str, object]) -> dict[str, object]:
        result = _happy_extract(payload)
        result["proposal"]["location"]["airportCode"] = None
        result["ambiguousFields"] = ["location.airportCode"]
        result["fieldConfidence"]["location.airportCode"] = 0.41
        return result

    client = _client(extract)
    response = client.post(
        f"{PREFIX}/intake/extractions",
        json={"text": "parking near the city airport", "category": "airport_parking"},
    )
    assert response.status_code == 200
    assert response.json()["ambiguousFields"] == ["location.airportCode"]
    assert response.json()["proposal"]["location"]["airportCode"] is None


def test_reversed_dates_are_closed_without_values() -> None:
    client = _client()
    extracted = client.post(
        f"{PREFIX}/intake/extractions",
        json={"text": JFK_TEXT, "category": "airport_parking"},
    )
    response = client.post(
        f"{PREFIX}/intake/intents",
        json={
            "intakeId": extracted.json()["intakeId"],
            **CONFIRMED,
            "start": "2026-09-08T22:00:00Z",
            "end": "2026-09-03T13:00:00Z",
        },
    )
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["field"] in {"service_window", "start", "end"}
    assert error["code"] == "end_must_follow_start"
    assert "2026-09-08" not in response.text
    assert "2026-09-03" not in response.text


def test_user_corrected_fields_are_used_not_raw_proposal() -> None:
    recorded: list[dict[str, object]] = []
    inner = build_facade()
    original = inner.create_purchase_intent

    def wrapped(payload: dict[str, object], **kwargs: object) -> Any:
        recorded.append(payload)
        return original(payload, **kwargs)  # type: ignore[misc]

    inner.create_purchase_intent = wrapped  # type: ignore[method-assign]
    client = _client(facade=inner)
    extracted = client.post(
        f"{PREFIX}/intake/extractions",
        json={"text": JFK_TEXT, "category": "airport_parking"},
    )
    response = client.post(
        f"{PREFIX}/intake/intents",
        json={
            "intakeId": extracted.json()["intakeId"],
            **CONFIRMED,
            "airportCode": "LAX",
            "shuttleMaxMinutes": 15,
        },
    )
    assert response.status_code == 200, response.text
    assert recorded[0]["location"]["airportCode"] == "LAX"
    assert recorded[0]["requirements"]["shuttleMaxMinutes"] == 15
    assert "text" not in recorded[0]
    assert JFK_TEXT not in str(recorded[0])
    assert response.json()["airport"] == "LAX"


def test_extract_failure_is_model_unavailable() -> None:
    def boom(_payload: dict[str, object]) -> dict[str, object]:
        raise RuntimeError(JFK_TEXT)

    client = _client(boom)
    response = client.post(
        f"{PREFIX}/intake/extractions",
        json={"text": JFK_TEXT, "category": "airport_parking"},
    )
    assert response.status_code in {400, 500}
    error = response.json()["error"]
    assert error["field"] == "model"
    assert error["code"] == "unavailable"
    assert JFK_TEXT not in response.text
    assert "flying from" not in response.text


def test_a3_rejects_foreign_offer() -> None:
    client = _client()
    first_id, first = _complete_through_a2(client)
    second_id, _second = _complete_through_a2(client)
    foreign = first["recommendedOfferId"]
    response = client.post(
        f"{PREFIX}/intake/intents/{second_id}/acceptances",
        json={"offerId": foreign, "offerVersion": 1},
    )
    assert response.status_code in {400, 409, 422}
    error = response.json()["error"]
    assert error["code"] in {"ineligible", "unknown_resource", "mismatch", "foreign"}
    assert first_id != second_id
    assert foreign not in response.text or error["field"] in {"offerId", "offer"}


def test_a4_replay_with_same_key_is_idempotent() -> None:
    client = _client()
    intent_id, dispatched = _complete_through_a2(client)
    accepted = client.post(
        f"{PREFIX}/intake/intents/{intent_id}/acceptances",
        json={"offerId": dispatched["recommendedOfferId"]},
    )
    assert accepted.status_code == 200
    key = "ik_01k2m3n4p5q6r7s8t9v0w1x2c9"
    first = client.post(
        f"{PREFIX}/intake/intents/{intent_id}/transaction-authorizations",
        headers={"Idempotency-Key": key},
        json={},
    )
    assert first.status_code == 200, first.text
    replay = client.post(
        f"{PREFIX}/intake/intents/{intent_id}/transaction-authorizations",
        headers={"Idempotency-Key": key},
        json={},
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["transaction"]["resultRef"] == first.json()["transaction"]["resultRef"]
    assert (
        replay.json()["transaction"]["authorizationId"]
        == first.json()["transaction"]["authorizationId"]
    )


def test_purchase_intent_payload_has_no_raw_text() -> None:
    recorded: list[dict[str, object]] = []
    inner = build_facade()
    original = inner.create_purchase_intent

    def wrapped(payload: dict[str, object], **kwargs: object) -> Any:
        recorded.append(payload)
        dumped = json_dumps(payload)
        assert "text" not in payload
        assert JFK_TEXT not in dumped
        assert "flying from" not in dumped
        return original(payload, **kwargs)  # type: ignore[misc]

    inner.create_purchase_intent = wrapped  # type: ignore[method-assign]
    client = _client(facade=inner)
    _extract_and_confirm(client)
    assert recorded
    assert "evidence" not in recorded[0]
    assert "confidence" not in recorded[0]


def json_dumps(value: object) -> str:
    import json

    return json.dumps(value)


def test_extract_client_application_error_stays_closed() -> None:
    def fail(_payload: dict[str, object]) -> dict[str, object]:
        raise ApplicationError("model", "unavailable")

    client = _client(fail)
    response = client.post(
        f"{PREFIX}/intake/extractions",
        json={"text": JFK_TEXT, "category": "airport_parking"},
    )
    assert response.status_code in {400, 500}
    assert response.json()["error"]["code"] == "unavailable"
    assert JFK_TEXT not in response.text


def test_unknown_intake_id_is_closed() -> None:
    client = _client()
    response = client.post(
        f"{PREFIX}/intake/intents",
        json={"intakeId": "in_01k2m3n4p5q6r7s8t9v0w1x2zz", **CONFIRMED},
    )
    assert response.status_code == 404
    assert response.json()["error"]["field"] == "intakeId"
    assert "in_01k2m3n4p5q6r7s8t9v0w1x2zz" not in response.text


def test_seeded_intent_cannot_use_intake_gates() -> None:
    from wp06_fakes import jfk_payload

    facade = build_facade()
    seeded = facade.create_purchase_intent(jfk_payload())
    client = _client(facade=facade)
    response = client.post(f"{PREFIX}/intake/intents/{seeded.intent_id}/confirm", json={})
    assert response.status_code == 404
    assert response.json()["error"]["field"] == "intentId"


def test_wrong_category_is_rejected() -> None:
    client = _client()
    response = client.post(
        f"{PREFIX}/intake/extractions",
        json={"text": JFK_TEXT, "category": "hotel"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "schema_invalid"
    assert JFK_TEXT not in response.text


def test_wall_clock_intent_is_not_already_expired() -> None:
    client = _client(facade=build_facade(clock=WallClock()))
    _intent_id, created = _extract_and_confirm(client)
    created_at = parse_utc(created["createdAt"], "createdAt")
    expires_at = parse_utc(created["expiresAt"], "expiresAt")
    now = datetime.now(UTC)
    assert expires_at > now
    assert expires_at - created_at == timedelta(hours=48)
    assert abs((created_at - now).total_seconds()) < 5


def _fake_model_extract(payload: dict[str, object]) -> dict[str, object]:
    result = compose_agent().extract(
        ExtractionRequest(
            text=str(payload["text"]),
            category=str(payload["category"]),
            correlation_id=str(payload["correlationId"]),
        )
    )
    return {
        "proposal": None if result.proposal is None else dict(result.proposal),
        "fieldConfidence": dict(result.field_confidence),
        "missingFields": list(result.missing_fields),
        "ambiguousFields": list(result.ambiguous_fields),
        "evidenceSpans": [
            {"field": item.field, "start": item.start, "end": item.end}
            for item in result.evidence_spans
        ],
        "requiresA1": True,
        "accepted": False,
        "fallback": result.fallback,
        "rejectionCode": result.rejection_code,
        "correlationId": payload["correlationId"],
    }


def test_fake_model_extract_of_spoken_ev_feeds_locked_ranker() -> None:
    spoken = (
        "Flying from JFK on September 3 at 1 PM, back September 8 at 10 PM. "
        "Standard EV, prefer covered parking, shuttle under 20 minutes."
    )
    client = _client(_fake_model_extract)
    extracted = client.post(
        f"{PREFIX}/intake/extractions",
        json={"text": spoken, "category": "airport_parking"},
    )
    assert extracted.status_code == 200, extracted.text
    proposal = extracted.json()["proposal"]
    assert proposal is not None
    assert proposal["constraints"]["accessibility"] == ["ev_charging"]
    confirmed = {
        "airportCode": proposal["location"]["airportCode"],
        "start": proposal["serviceWindow"]["start"],
        "end": proposal["serviceWindow"]["end"],
        "vehicleClass": proposal["requirements"]["vehicleClass"],
        "covered": proposal["requirements"]["covered"],
        "shuttleMaxMinutes": proposal["requirements"]["shuttleMaxMinutes"],
        "currency": proposal["constraints"]["currency"],
        "accessibility": proposal["constraints"]["accessibility"],
    }
    created = client.post(
        f"{PREFIX}/intake/intents",
        json={"intakeId": extracted.json()["intakeId"], **confirmed},
    )
    assert created.status_code == 200, created.text
    intent_id = created.json()["intentId"]
    a1 = client.post(f"{PREFIX}/intake/intents/{intent_id}/confirm", json={})
    assert a1.status_code == 200, a1.text
    a2 = client.post(f"{PREFIX}/intake/intents/{intent_id}/dispatch", json={})
    assert a2.status_code == 200, a2.text
    ranked = a2.json()["offers"]
    by_rank = {item["rank"]: item for item in ranked}
    assert set(by_rank) == {1, 2, 3}
    recommended = a2.json()["recommendedOfferId"]
    winner = next(item for item in ranked if item["offerId"] == recommended)
    assert winner["rank"] == 1
    assert "scoreMicros" not in winner
    assert winner["price"]["totalMinor"] == 14800
    assert a2.json()["downside"]["delta"] == 2900
