"""COMP-G1-06: task mutation stays local; supplier views omit parent, siblings, preferences."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass

import pytest
from wp04_helpers import A1_ID, A2_ID  # type: ignore[import-not-found]
from wp06_fakes import (  # type: ignore[import-not-found]
    FixtureRoster,
    build_facade,
    governance,
    intent_id,
    jfk_payload,
)

from itaa_application.compatibility import CompatibilityAdapter
from itaa_application.cost_ledger_projection import (
    LedgerOfferInput,
    LedgerTaskInput,
    project_cost_ledger,
)
from itaa_application.errors import ApplicationError
from itaa_application.orchestration import OrchestrationService, supplier_bound_fields
from itaa_application.plan_projection import PlanTaskInput, project_plan
from itaa_domain.booking_task_states import BookingTaskState
from itaa_domain.intent_states import (
    IntentState,
    ParentLifecycle,
    TaskMembership,
    TaskProjectionInput,
    project_intent_state,
)

PI_BODY = "01k2m3n4p5q6r7s8t9v0w1x2y3"
TASK_A = "bt_01k2m3n4p5q6r7s8t9v0w1x2p4"
TASK_B = "bt_01k2m3n4p5q6r7s8t9v0w1x2p5"
INTENT = "oi_01k2m3n4p5q6r7s8t9v0w1x2p1"
PLAN = "pl_01k2m3n4p5q6r7s8t9v0w1x2p2"
LEDGER = "ld_01k2m3n4p5q6r7s8t9v0w1x2p3"

SUPPLIER_FORBIDDEN = (
    "conversation",
    "conversationId",
    "conversationEvents",
    "parentIntent",
    "parentIntentId",
    "orchestrationIntent",
    "orchestrationIntentId",
    "siblingTasks",
    "siblingTaskIds",
    "siblings",
    "plan",
    "planId",
    "competitorOffers",
    "competitorOfferIds",
    "preferences",
    "preferenceHistory",
    "buyerToken",
    "buyerId",
    "actorId",
    "ownerId",
    "scoreMicros",
)

PREFERENCE_MARKERS = (
    "preferences",
    "preferenceHistory",
    "MUST-HAVES",
    "CEILING",
)


def _blob(value: object) -> str:
    if is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    return json.dumps(value, default=str, sort_keys=True)


def _walk(node: object) -> object:
    if is_dataclass(node) and not isinstance(node, type):
        return _walk(asdict(node))
    if isinstance(node, Mapping):
        return {str(key): _walk(child) for key, child in node.items()}
    if isinstance(node, tuple | list):
        return [_walk(child) for child in node]
    return node


def _task(membership: str, state: str) -> TaskProjectionInput:
    return TaskProjectionInput(
        membership=TaskMembership(membership),
        state=BookingTaskState(state),
    )


def _plan_task(task_id: str, membership: str, state: str) -> PlanTaskInput:
    return PlanTaskInput(
        task_id=task_id,
        membership=TaskMembership(membership),
        state=BookingTaskState(state),
    )


def _ledger_task(
    task_id: str,
    state: str,
    *,
    total_minor: int,
    currency: str = "USD",
    validity: str = "valid",
    recommended: bool = True,
    selected: bool = False,
    authorized: bool = False,
) -> LedgerTaskInput:
    return LedgerTaskInput(
        task_id=task_id,
        state=BookingTaskState(state),
        offers=(
            LedgerOfferInput(
                total_minor=total_minor,
                currency=currency,
                validity=validity,
                tax_minor=0,
                fees_minor=0,
                recommended=recommended,
                selected=selected,
                authorized=authorized,
            ),
        ),
    )


def _row_for(ledger: Mapping[str, object], task_id: str) -> dict[str, object]:
    rows = ledger["rows"]
    assert isinstance(rows, list)
    matches = [row for row in rows if isinstance(row, Mapping) and row["taskId"] == task_id]
    assert len(matches) == 1, f"ledger must have exactly one row for {task_id}"
    return dict(matches[0])


def test_invalidating_task_a_does_not_change_task_b_parent_membership() -> None:
    before = (
        _task("accepted", "offers_ready"),
        _task("accepted", "a3_review"),
    )
    after = (
        _task("accepted", "a1_review"),
        _task("accepted", "a3_review"),
    )
    assert project_intent_state(overlay=ParentLifecycle("none"), tasks=before) == IntentState(
        "attention"
    )
    assert project_intent_state(overlay=ParentLifecycle("none"), tasks=after) == IntentState(
        "attention"
    )
    assert after[1].state == BookingTaskState("a3_review")
    assert after[1].membership == TaskMembership("accepted")
    assert before[1].state == after[1].state


def test_mutating_task_a_does_not_change_task_b_plan_or_ledger_row() -> None:
    plan_before = project_plan(
        INTENT,
        PLAN,
        (
            _plan_task(TASK_A, "accepted", "offers_ready"),
            _plan_task(TASK_B, "accepted", "offers_ready"),
        ),
    )
    plan_after = project_plan(
        INTENT,
        PLAN,
        (
            _plan_task(TASK_A, "accepted", "a1_review"),
            _plan_task(TASK_B, "accepted", "offers_ready"),
        ),
    )
    before_ids = plan_before["taskIds"]
    after_ids = plan_after["taskIds"]
    assert before_ids == [TASK_A, TASK_B]
    assert after_ids == [TASK_A, TASK_B]
    assert isinstance(after_ids, list)
    assert after_ids[1] == TASK_B

    ledger_before = project_cost_ledger(
        INTENT,
        LEDGER,
        (
            _ledger_task(TASK_A, "offers_ready", total_minor=14800),
            _ledger_task(TASK_B, "offers_ready", total_minor=8900, currency="GBP"),
        ),
        simulation=True,
    )
    ledger_after = project_cost_ledger(
        INTENT,
        LEDGER,
        (
            _ledger_task(
                TASK_A,
                "authorized_simulated",
                total_minor=14800,
                selected=True,
                authorized=True,
            ),
            _ledger_task(TASK_B, "offers_ready", total_minor=8900, currency="GBP"),
        ),
        simulation=True,
    )
    assert _row_for(ledger_before, TASK_B) == _row_for(ledger_after, TASK_B)
    assert _row_for(ledger_after, TASK_A)["authorizedSimulatedMinor"] == 14800
    assert _row_for(ledger_after, TASK_B)["authorizedSimulatedMinor"] == 0
    assert _row_for(ledger_after, TASK_B)["estimatedMinor"] == 8900


def test_supplier_bound_projection_omits_parent_siblings_preferences_and_buyer() -> None:
    tainted = {
        "schemaVersion": "1.0",
        "taskId": TASK_A,
        "intentId": INTENT,
        "domain": "parking",
        "state": "offers_ready",
        "simulation": True,
        "conversation": {"id": "cv_leak"},
        "conversationId": "cv_leak",
        "parentIntent": {"intentId": INTENT},
        "parentIntentId": INTENT,
        "siblingTasks": [TASK_B],
        "siblingTaskIds": [TASK_B],
        "plan": {"planId": PLAN},
        "planId": PLAN,
        "competitorOffers": [{"offerId": "of_01k2m3n4p5q6r7s8t9v0w1x2a1"}],
        "preferences": {"covered": "preferred"},
        "preferenceHistory": [{"key": "covered"}],
        "buyerToken": "bs_01k2m3n4p5q6r7s8t9v0w1x2y4",
        "buyerId": "ar_01k2m3n4p5q6r7s8t9v0w1x2y5",
    }
    bound = _walk(supplier_bound_fields(tainted))
    blob = _blob(bound)
    assert isinstance(bound, Mapping)
    for field in SUPPLIER_FORBIDDEN:
        assert field not in bound
        assert field not in blob
    assert TASK_B not in blob
    assert "bs_01k2m3n4p5q6r7s8t9v0w1x2y4" not in blob


def test_preferences_never_enter_a2_shaped_supplier_payloads() -> None:
    roster = FixtureRoster()
    facade = build_facade(roster=roster)
    facade.create_purchase_intent(jfk_payload())
    facade.confirm_requirement(intent_id(), governance(A1_ID))
    facade.approve_and_dispatch(intent_id(), governance(A2_ID))
    for envelopes in (list(port.seen_envelopes) for port in roster.ports().values()):
        assert envelopes
        blob = _blob(envelopes)
        for marker in PREFERENCE_MARKERS:
            assert marker not in blob
        assert "scoreMicros" not in blob

    parking_task = {
        "taskId": f"bt_{PI_BODY}",
        "intentId": f"oi_{PI_BODY}",
        "domain": "parking",
        "state": "researching",
        "simulation": True,
        "preferences": {"covered": "preferred"},
        "preferenceHistory": [{"key": "covered"}],
    }
    bound = _walk(supplier_bound_fields(parking_task))
    blob = _blob(bound)
    for marker in PREFERENCE_MARKERS:
        assert marker not in blob


def test_orchestration_task_read_does_not_expose_sibling_or_conversation() -> None:
    facade = build_facade()
    facade.create_purchase_intent(jfk_payload())
    service = OrchestrationService(facade, CompatibilityAdapter())
    with pytest.raises(ApplicationError) as missing:
        service.get_task(f"oi_{PI_BODY}", TASK_B)
    assert missing.value.code == "unknown_resource"
    assert missing.value.field == "taskId"
    task = service.get_task(f"oi_{PI_BODY}", f"bt_{PI_BODY}")
    blob = _blob(task)
    assert "conversation" not in blob
    assert "sibling" not in blob
    assert "scoreMicros" not in blob
    assert TASK_B not in blob
