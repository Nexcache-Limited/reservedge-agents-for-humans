"""Raw intake text must never enter PurchaseIntent, snapshots, or closed errors."""

from __future__ import annotations

import json
from collections.abc import Mapping

from fastapi.testclient import TestClient

from itaa_api.composition import build_facade
from itaa_api.intake import PREFIX, build_intake_app
from itaa_application.session_models import BuyerSnapshot

JFK_PARAGRAPH = (
    "I'm flying from JFK on September 3 at 1 PM and returning September 8 at 10 PM. "
    "I have a standard EV, prefer covered parking, and don't want a shuttle longer than 20 minutes."
)
NEEDLES = (
    JFK_PARAGRAPH,
    "flying from JFK",
    "September 3 at 1 PM",
    "don't want a shuttle longer",
    "standard EV, prefer covered",
)


def _extract(payload: dict[str, object]) -> dict[str, object]:
    return {
        "proposal": {
            "category": "airport_parking",
            "location": {"airportCode": "JFK"},
            "serviceWindow": {"start": "2026-09-03T13:00:00Z", "end": "2026-09-08T22:00:00Z"},
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


def _assert_clean(blob: object) -> None:
    text = blob if isinstance(blob, str) else json.dumps(blob)
    for needle in NEEDLES:
        assert needle not in text


def test_raw_paragraph_never_enters_intent_outcomes_or_errors() -> None:
    recorded: list[dict[str, object]] = []
    inner = build_facade()
    original = inner.create_purchase_intent

    def wrapped(payload: Mapping[str, object], *, portfolio_id: str | None = None) -> BuyerSnapshot:
        recorded.append(dict(payload))
        _assert_clean(payload)
        return original(payload, portfolio_id=portfolio_id)

    inner.create_purchase_intent = wrapped  # type: ignore[method-assign]
    client = TestClient(build_intake_app(inner, extract_client=_extract))

    extracted = client.post(
        f"{PREFIX}/intake/extractions",
        json={"text": JFK_PARAGRAPH, "category": "airport_parking"},
    )
    assert extracted.status_code == 200
    created = client.post(
        f"{PREFIX}/intake/intents",
        json={
            "intakeId": extracted.json()["intakeId"],
            "airportCode": "JFK",
            "start": "2026-09-03T13:00:00Z",
            "end": "2026-09-08T22:00:00Z",
            "vehicleClass": "standard",
            "covered": "preferred",
            "shuttleMaxMinutes": 20,
            "currency": "USD",
            "accessibility": ["ev_charging"],
        },
    )
    assert created.status_code == 200
    _assert_clean(created.json())
    assert recorded
    assert "text" not in recorded[0]

    intent_id = created.json()["intentId"]
    confirmed = client.post(f"{PREFIX}/intake/intents/{intent_id}/confirm", json={})
    dispatched = client.post(f"{PREFIX}/intake/intents/{intent_id}/dispatch", json={})
    assert dispatched.status_code == 200
    _assert_clean(dispatched.json())
    _assert_clean(dispatched.json()["supplierOutcomes"])
    _assert_clean(dispatched.json()["offers"])

    failed = client.post(
        f"{PREFIX}/intake/intents",
        json={
            "intakeId": extracted.json()["intakeId"],
            "airportCode": "JFK",
            "start": "2026-09-08T22:00:00Z",
            "end": "2026-09-03T13:00:00Z",
            "vehicleClass": "standard",
            "covered": "preferred",
            "shuttleMaxMinutes": 20,
            "currency": "USD",
        },
    )
    assert failed.status_code == 400
    _assert_clean(failed.json())
    _assert_clean(failed.text)
    _assert_clean(confirmed.json())
