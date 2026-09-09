"""COMP-G1-06 Phase 2: unknown resources, malformed ids, and durability honesty."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from wp06_fakes import build_facade, jfk_payload  # type: ignore[import-not-found]

from itaa_api.app import create_app
from itaa_application.compatibility import ResolvedKind, resolve_orchestration_ref
from itaa_application.errors import ApplicationError
from itaa_application.orchestration import OrchestrationService

ORCH = "/v1/orchestration"


def test_malformed_orchestration_identifier_is_invalid_opaque_syntax() -> None:
    ref = resolve_orchestration_ref("not-an-id")
    assert ref.kind is ResolvedKind.MALFORMED
    service = OrchestrationService(build_facade())
    with pytest.raises(ApplicationError) as raised:
        service.get_intent("not-an-id")
    assert raised.value.field == "intentId"
    assert raised.value.code == "invalid_opaque_syntax"
    response = TestClient(create_app(build_facade())).get(f"{ORCH}/intents/not-an-id")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_opaque_syntax"


def test_unknown_canonical_intent_is_unknown_resource() -> None:
    client = TestClient(create_app(build_facade()))
    response = client.get(f"{ORCH}/intents/oi_01k2m3n4p5q6r7s8t9v0w1x2z9")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "unknown_resource"
    assert body["error"]["field"] == "intentId"


def test_new_process_memory_does_not_resume_prior_session() -> None:
    first = TestClient(create_app(build_facade()))
    created = first.post("/v1/simulations/airport-parking/intents", json=jfk_payload())
    assert created.status_code == 200
    wrapped = first.get(f"{ORCH}/intents/{created.json()['intentId']}")
    assert wrapped.status_code == 200
    restarted = TestClient(create_app(build_facade()))
    ghost = restarted.get(f"{ORCH}/intents/{created.json()['intentId']}")
    assert ghost.status_code == 404
    assert ghost.json()["error"]["code"] == "unknown_resource"


def test_readyz_declares_unsupported_durability() -> None:
    client = TestClient(create_app())
    ready = client.get("/readyz")
    assert ready.status_code == 200
    assert ready.json()["durability"] == "unsupported"
