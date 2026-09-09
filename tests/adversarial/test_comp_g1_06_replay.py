"""COMP-G1-06 Phase 2: repeated pi_* wraps and orchestration reads stay idempotent."""

from __future__ import annotations

from fastapi.testclient import TestClient
from wp06_fakes import build_facade, intent_id, jfk_payload  # type: ignore[import-not-found]

from itaa_api.app import create_app
from itaa_application.compatibility import (
    CompatibilityAdapter,
    ResolvedKind,
    resolve_orchestration_ref,
)
from itaa_application.orchestration import OrchestrationService

ORCH = "/v1/orchestration"
BODY = "01k2m3n4p5q6r7s8t9v0w1x2y3"


def test_repeated_wrap_of_the_same_session_reuses_canonical_ids() -> None:
    facade = build_facade()
    facade.create_purchase_intent(jfk_payload())
    session = facade.lookup_session(intent_id())
    assert session is not None
    adapter = CompatibilityAdapter()
    first = adapter.wrap_purchase_intent(session)
    second = adapter.wrap_purchase_intent(session)
    assert first == second
    assert first is second
    assert first.orchestration_intent_id == f"oi_{BODY}"
    assert first.booking_task_id == f"bt_{BODY}"
    assert first.plan_id == f"pl_{BODY}"
    assert first.ledger_id == f"ld_{BODY}"


def test_alias_and_canonical_reads_return_the_same_intent() -> None:
    facade = build_facade()
    facade.create_purchase_intent(jfk_payload())
    service = OrchestrationService(facade)
    alias = resolve_orchestration_ref(f"pi_{BODY}")
    canonical = resolve_orchestration_ref(f"oi_{BODY}")
    assert alias.kind is ResolvedKind.PURCHASE_ALIAS
    assert canonical.kind is ResolvedKind.ORCHESTRATION
    first = service.get_intent(f"pi_{BODY}")
    second = service.get_intent(f"oi_{BODY}")
    third = service.get_intent(f"pi_{BODY}")
    assert first == second == third
    assert first["intentId"] == f"oi_{BODY}"
    assert "scoreMicros" not in first


def test_http_orchestration_get_is_idempotent() -> None:
    client = TestClient(create_app(build_facade()))
    created = client.post("/v1/simulations/airport-parking/intents", json=jfk_payload())
    assert created.status_code == 200
    raw = created.json()["intentId"]
    first = client.get(f"{ORCH}/intents/{raw}")
    second = client.get(f"{ORCH}/intents/{raw}")
    canonical = client.get(f"{ORCH}/intents/oi_{BODY}")
    assert first.status_code == 200
    assert first.json() == second.json() == canonical.json()
    assert first.json()["intentId"] == f"oi_{BODY}"
    assert first.json()["durability"] == "unsupported"
