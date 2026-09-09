from __future__ import annotations

from fastapi.testclient import TestClient
from wp08_helpers import CORRELATION, JFK_TEXT, locked_ranking_facts

from itaa_google_adapter.app import (
    CLOUDFLARE_PAGES_PLACEHOLDER,
    DEFAULT_CORS_ORIGIN,
    create_google_app,
    documented_cors_origins,
)


def test_health_and_readiness_remain_on_wrapper() -> None:
    client = TestClient(create_google_app())
    live = client.get("/healthz")
    ready = client.get("/readyz")
    assert live.status_code == 200
    assert ready.status_code == 200
    assert live.json() == {"status": "ok", "environment": "local_simulation"}
    assert ready.json()["durability"] == "unsupported"
    dumped = live.text + ready.text
    assert "secret" not in dumped
    assert "api_key" not in dumped
    assert ("AI" + "za") not in dumped


def test_google_extraction_and_explanation_routes() -> None:
    client = TestClient(create_google_app())
    extracted = client.post(
        "/v1/google/extractions",
        json={"text": JFK_TEXT, "category": "airport_parking", "correlationId": CORRELATION},
    )
    assert extracted.status_code == 200
    body = extracted.json()
    assert body["requiresA1"] is True
    assert body["accepted"] is False
    assert body["proposal"]["location"]["airportCode"] == "JFK"
    assert "intentId" not in body["proposal"]
    assert "buyerToken" not in body["proposal"]
    assert body["fieldAttributions"]
    assert all("origin" in item and "confidence" in item for item in body["fieldAttributions"])
    facts = locked_ranking_facts()
    explained = client.post(
        "/v1/google/explanations",
        json={
            "correlationId": CORRELATION,
            "recommendedOfferId": facts.winner_id,
            "winnerDisplayName": facts.winner_display_name,
            "offers": [
                {
                    "supplierToken": item.supplier_token,
                    "displayName": item.display_name,
                    "offerId": item.offer_id,
                    "rank": item.rank,
                    "scoreMicros": item.score_micros,
                    "totalMinor": item.total_minor,
                    "currency": item.currency,
                    "recommended": item.recommended,
                }
                for item in facts.offers
            ],
            "downside": {"dimension": facts.downside_dimension, "delta": facts.downside_delta},
        },
    )
    assert explained.status_code == 200
    assert "SkyShield" in explained.json()["explanation"]
    assert explained.json()["grounded"] is True


def test_core_simulation_routes_still_work() -> None:
    client = TestClient(create_google_app())
    from wp06_fakes import jfk_payload

    created = client.post("/v1/simulations/airport-parking/intents", json=jfk_payload())
    assert created.status_code == 200
    assert created.json()["simulation"] is True


def test_cors_allowlist() -> None:
    client = TestClient(create_google_app())
    allowed = client.get("/healthz", headers={"Origin": DEFAULT_CORS_ORIGIN})
    assert allowed.headers.get("access-control-allow-origin") == DEFAULT_CORS_ORIGIN
    denied = client.get("/healthz", headers={"Origin": "https://evil.example"})
    assert denied.headers.get("access-control-allow-origin") != "https://evil.example"
    assert CLOUDFLARE_PAGES_PLACEHOLDER in documented_cors_origins()


def test_unknown_extraction_fields_fail_closed() -> None:
    client = TestClient(create_google_app())
    response = client.post(
        "/v1/google/extractions",
        json={
            "text": JFK_TEXT,
            "category": "airport_parking",
            "correlationId": CORRELATION,
            "apiKey": "should-not-be-accepted",
        },
    )
    assert response.status_code == 400
    assert "should-not-be-accepted" not in response.text
    assert response.json()["error"]["field"] == "payload"
