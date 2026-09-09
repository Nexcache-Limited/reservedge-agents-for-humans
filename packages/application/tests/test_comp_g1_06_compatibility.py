from __future__ import annotations

from dataclasses import replace

import pytest
from wp06_fakes import build_facade, intent_id, jfk_payload

from itaa_application.compatibility import (
    CompatibilityAdapter,
    ResolvedKind,
    resolve_orchestration_ref,
    wrapper_ids_from_purchase_intent,
)
from itaa_application.errors import ApplicationError
from itaa_application.orchestration import OrchestrationService
from itaa_application.session_models import BuyerSessionState

BODY = "01k2m3n4p5q6r7s8t9v0w1x2y3"
PI = "pi_" + BODY
OI = "oi_" + BODY
BT = "bt_" + BODY
PL = "pl_" + BODY
LD = "ld_" + BODY


def test_resolve_orchestration_ref_kinds() -> None:
    assert resolve_orchestration_ref(OI).kind is ResolvedKind.ORCHESTRATION
    assert resolve_orchestration_ref(PI).kind is ResolvedKind.PURCHASE_ALIAS
    assert resolve_orchestration_ref("not-an-id").kind is ResolvedKind.MALFORMED
    assert resolve_orchestration_ref("oi_short").kind is ResolvedKind.MALFORMED
    assert resolve_orchestration_ref("pi_01k2m3n4p5q6r7s8t9v0w1x2yI").kind is ResolvedKind.MALFORMED
    adapter = CompatibilityAdapter()
    assert adapter.resolve_orchestration_ref(OI).value == OI


def test_wrap_reuses_crockford_body_and_is_idempotent() -> None:
    facade = build_facade()
    facade.create_purchase_intent(jfk_payload())
    session = facade.lookup_session(intent_id())
    assert session is not None
    adapter = CompatibilityAdapter()
    first = adapter.wrap_purchase_intent(session)
    second = adapter.wrap_purchase_intent(session)
    assert first is second
    assert first.purchase_intent_id == PI
    assert first.orchestration_intent_id == OI
    assert first.booking_task_id == BT
    assert first.plan_id == PL
    assert first.ledger_id == LD
    again = wrapper_ids_from_purchase_intent(PI)
    assert again.orchestration_intent_id == OI
    assert adapter.purchase_intent_id_for(OI) == PI


def test_wrap_is_stable_across_session_mutation() -> None:
    facade = build_facade()
    facade.create_purchase_intent(jfk_payload())
    session = facade.lookup_session(intent_id())
    assert session is not None
    adapter = CompatibilityAdapter()
    before = adapter.wrap_purchase_intent(session)
    mutated = replace(session, state=BuyerSessionState.OFFERS_RANKED)
    after = adapter.wrap_purchase_intent(mutated)
    assert after == before


def test_malformed_purchase_intent_is_invalid_opaque_syntax() -> None:
    with pytest.raises(ApplicationError) as caught:
        wrapper_ids_from_purchase_intent("oi_" + BODY)
    assert caught.value.field == "intentId"
    assert caught.value.code == "invalid_opaque_syntax"
    with pytest.raises(ApplicationError) as caught:
        wrapper_ids_from_purchase_intent("garbage")
    assert caught.value.field == "intentId"
    assert caught.value.code == "invalid_opaque_syntax"


def test_unknown_resource_when_session_missing() -> None:
    service = OrchestrationService(build_facade())
    with pytest.raises(ApplicationError) as caught:
        service.get_intent(PI)
    assert caught.value.field == "intentId"
    assert caught.value.code == "unknown_resource"
    with pytest.raises(ApplicationError) as caught:
        service.get_intent(OI)
    assert caught.value.field == "intentId"
    assert caught.value.code == "unknown_resource"


def test_malformed_refs_use_closed_codes() -> None:
    service = OrchestrationService(build_facade())
    with pytest.raises(ApplicationError) as caught:
        service.get_intent("not-valid")
    assert caught.value.field == "intentId"
    assert caught.value.code == "invalid_opaque_syntax"
    facade = build_facade()
    facade.create_purchase_intent(jfk_payload())
    wrapped = OrchestrationService(facade)
    with pytest.raises(ApplicationError) as caught:
        wrapped.get_task(PI, "task-nope")
    assert caught.value.field == "taskId"
    assert caught.value.code == "invalid_opaque_syntax"
    with pytest.raises(ApplicationError) as caught:
        wrapped.get_task(PI, "bt_01k2m3n4p5q6r7s8t9v0w1x2zz")
    assert caught.value.field == "taskId"
    assert caught.value.code == "unknown_resource"


def test_canonical_and_alias_resolve_the_same_wrapper() -> None:
    facade = build_facade()
    facade.create_purchase_intent(jfk_payload())
    service = OrchestrationService(facade)
    via_pi = service.get_intent(PI)
    via_oi = service.get_intent(OI)
    assert via_pi == via_oi
    assert via_pi["intentId"] == OI
