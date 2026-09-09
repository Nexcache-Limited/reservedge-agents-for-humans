from __future__ import annotations

import pytest
from comp_aws_01_helpers import CORRELATION, DEMO_A, DEMO_B, DEMO_C, GENERIC
from fastapi.testclient import TestClient
from wp06_fakes import jfk_payload

from itaa_aws_adapter.app import (
    CLOUDFLARE_PAGES_PLACEHOLDER,
    DEFAULT_CORS_ORIGIN,
    create_aws_app,
    documented_cors_origins,
)


def test_health_and_fake_readyz() -> None:
    client = TestClient(create_aws_app())
    live = client.get("/healthz")
    ready = client.get("/readyz")
    assert live.status_code == 200
    assert ready.status_code == 200
    assert live.json() == {"status": "ok", "environment": "local_simulation"}
    assert ready.json()["durability"] == "unsupported"
    dumped = (live.text + ready.text).lower()
    assert "secret" not in dumped
    assert "api_key" not in dumped
    assert "bedrock" not in dumped


def test_plan_turns_demo_a_and_rejects_extra_fields() -> None:
    client = TestClient(create_aws_app())
    ok = client.post(
        "/v1/aws/plan-turns",
        json={"objective": DEMO_A, "correlationId": CORRELATION},
    )
    assert ok.status_code == 200
    body = ok.json()
    parking = next(item for item in body["projection"]["tasks"] if item["kind"] == "parking")
    assert parking["provenance"] == "explicit"
    assert parking["support"] == "live_simulated"
    assert all(
        item["kind"] != "hotel" or item["provenance"] != "explicit"
        for item in body["projection"]["tasks"]
    )
    assert "intentId" not in body["planTurn"]
    extra = client.post(
        "/v1/aws/plan-turns",
        json={
            "objective": DEMO_A,
            "correlationId": CORRELATION,
            "apiKey": "should-not-be-accepted",
        },
    )
    assert extra.status_code == 400
    assert extra.json()["error"]["field"] == "payload"
    assert "should-not-be-accepted" not in extra.text


def test_plan_turns_demos_b_and_c_and_generic() -> None:
    client = TestClient(create_aws_app())
    demo_b = client.post("/v1/aws/plan-turns", json={"objective": DEMO_B}).json()["projection"]
    by_kind = {item["kind"]: item for item in demo_b["tasks"]}
    assert by_kind["rental"]["provenance"] == "explicit"
    assert by_kind["parking"]["provenance"] == "inferred"
    assert by_kind["hotel"]["provenance"] == "proposed"
    demo_c = client.post("/v1/aws/plan-turns", json={"objective": DEMO_C}).json()["projection"]
    assert demo_c["phase"] == "clarify"
    assert demo_c["facts"]["parkingAirport"] != "JFK"
    generic = client.post("/v1/aws/plan-turns", json={"objective": GENERIC})
    blob = generic.text.lower()
    assert generic.status_code == 200
    assert "jfk" not in blob
    assert "skyshield" not in blob


def test_execute_turns_prepare_and_unknown_tool() -> None:
    client = TestClient(create_aws_app())
    prepared = client.post(
        "/v1/aws/execute-turns",
        json={
            "tool": "prepare_parking_requirement",
            "payload": {"objective": DEMO_A, "planConfirmed": True},
            "correlationId": CORRELATION,
        },
        headers={"x-correlation-id": CORRELATION},
    )
    assert prepared.status_code == 200
    result = prepared.json()["result"]
    assert result["airportCode"] == "JFK"
    assert "intentId" not in result
    unknown = client.post(
        "/v1/aws/execute-turns",
        json={"tool": "rank_offers", "payload": {}, "correlationId": CORRELATION},
        headers={"x-correlation-id": CORRELATION},
    )
    assert unknown.status_code == 500
    assert unknown.json()["error"] == {
        "code": "closed",
        "field": "tool",
        "correlationId": CORRELATION,
    }


def test_core_simulation_routes_still_work() -> None:
    client = TestClient(create_aws_app())
    created = client.post("/v1/simulations/airport-parking/intents", json=jfk_payload())
    assert created.status_code == 200
    assert created.json()["simulation"] is True


def test_combined_process_agent_sessions_do_not_http_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ITAA_AWS_ADAPTER_URL", "http://127.0.0.1:1")
    client = TestClient(create_aws_app())
    created = client.post("/v1/agent/sessions", json={"objective": DEMO_A})
    assert created.status_code == 200, created.text
    body = created.json()
    parking = next(item for item in body["projection"]["tasks"] if item["kind"] == "parking")
    assert parking["provenance"] == "explicit"
    assert body["sessionId"].startswith("as_")
    assert "planTurn" not in body


def test_cors_allowlist() -> None:
    client = TestClient(create_aws_app())
    allowed = client.get("/healthz", headers={"Origin": DEFAULT_CORS_ORIGIN})
    assert allowed.headers.get("access-control-allow-origin") == DEFAULT_CORS_ORIGIN
    denied = client.get("/healthz", headers={"Origin": "https://evil.example"})
    assert denied.headers.get("access-control-allow-origin") != "https://evil.example"
    assert CLOUDFLARE_PAGES_PLACEHOLDER in documented_cors_origins()


def test_live_readyz_without_sdk_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITAA_AWS_MODEL_MODE", "live")
    monkeypatch.setenv("ITAA_AWS_TIMEOUT_MS", "30000")
    import itaa_aws_adapter.live as live_mod

    monkeypatch.setattr(live_mod, "_SDK_MODULE", "strands_agents_not_installed")
    client = TestClient(create_aws_app())
    ready = client.get("/readyz")
    assert ready.status_code == 503
    assert ready.json() == {
        "status": "unavailable",
        "adapter": "live",
        "environment": "local_simulation",
    }
    dumped = ready.text.lower()
    assert "account" not in dumped
    assert "credential" not in dumped


def test_unknown_mode_readyz_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITAA_AWS_MODEL_MODE", "maybe")
    client = TestClient(create_aws_app())
    ready = client.get("/readyz")
    assert ready.status_code == 503
    assert ready.json()["adapter"] == "unknown"
    plan = client.post("/v1/aws/plan-turns", json={"objective": DEMO_A})
    assert plan.status_code == 400
    assert plan.json()["error"]["field"] == "model"
    assert plan.json()["error"]["code"] == "schema_invalid"


def test_live_plan_turn_does_not_return_fake(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITAA_AWS_MODEL_MODE", "live")
    monkeypatch.setenv("ITAA_AWS_TIMEOUT_MS", "30000")
    client = TestClient(create_aws_app())
    response = client.post("/v1/aws/plan-turns", json={"objective": DEMO_A})
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "unavailable"
    assert body["error"]["field"] == "model"
    assert "projection" not in body
    assert "planTurn" not in body
