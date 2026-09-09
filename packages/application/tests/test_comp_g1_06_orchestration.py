from __future__ import annotations

from dataclasses import replace

from wp04_helpers import A1_ID, A2_ID
from wp06_fakes import (
    accept_command,
    authorize_command,
    build_facade,
    governance,
    intent_id,
    jfk_payload,
)

from itaa_application.orchestration import (
    OrchestrationService,
    map_buyer_session,
    supplier_bound_fields,
)
from itaa_application.plan_projection import PlanTaskInput, project_plan
from itaa_application.session_models import BuyerSessionState
from itaa_domain.booking_task_states import BookingTaskState
from itaa_domain.intent_states import ParentLifecycle, TaskMembership

BODY = "01k2m3n4p5q6r7s8t9v0w1x2y3"
OI = "oi_" + BODY
BT = "bt_" + BODY
PI = "pi_" + BODY


def _service_at(state: str) -> tuple[OrchestrationService, object]:
    facade = build_facade()
    facade.create_purchase_intent(jfk_payload())
    if state != "created":
        facade.confirm_requirement(intent_id(), governance(A1_ID))
    if state in {"dispatched", "accepted", "authorized"}:
        dispatched = facade.approve_and_dispatch(intent_id(), governance(A2_ID))
        if state in {"accepted", "authorized"}:
            winner = next(item for item in dispatched.offers if item.recommended)
            accepted = facade.accept_recommended_or_selected_offer(
                intent_id(), accept_command(winner.offer_id)
            )
            if state == "authorized":
                assert accepted.acceptance is not None
                facade.authorize_simulated_transaction(
                    intent_id(),
                    authorize_command(
                        acceptance_id=accepted.acceptance.acceptance_id,
                        amount_minor=winner.total_minor,
                        supplier_token=winner.supplier_token,
                    ),
                )
    return OrchestrationService(facade), facade


def test_buyer_session_mapping_table() -> None:
    service, facade = _service_at("created")
    session = facade.lookup_session(intent_id())
    assert session is not None
    assert map_buyer_session(session) == (ParentLifecycle.NONE, BookingTaskState.A1_REVIEW)
    assert service.get_intent(PI)["state"] == "attention"
    service, facade = _service_at("confirmed")
    session = facade.lookup_session(intent_id())
    assert session is not None
    assert map_buyer_session(session) == (ParentLifecycle.NONE, BookingTaskState.A2_REQUIRED)
    assert service.get_intent(PI)["state"] == "attention"
    service, facade = _service_at("dispatched")
    session = facade.lookup_session(intent_id())
    assert session is not None
    assert map_buyer_session(session) == (ParentLifecycle.NONE, BookingTaskState.OFFERS_READY)
    assert service.get_intent(PI)["state"] == "offers_ready"
    service, facade = _service_at("accepted")
    session = facade.lookup_session(intent_id())
    assert session is not None
    assert map_buyer_session(session) == (ParentLifecycle.NONE, BookingTaskState.A4_REQUIRED)
    assert service.get_intent(PI)["state"] == "attention"
    service, facade = _service_at("authorized")
    session = facade.lookup_session(intent_id())
    assert session is not None
    assert map_buyer_session(session) == (
        ParentLifecycle.NONE,
        BookingTaskState.AUTHORIZED_SIMULATED,
    )
    parent = service.get_intent(PI)
    assert parent["state"] == "completed_simulated"
    assert parent["state"] != "completed"
    assert parent["state"] != "partially_booked"


def test_cancelled_before_and_after_a2() -> None:
    _service, facade = _service_at("created")
    session = facade.lookup_session(intent_id())
    assert session is not None
    early = replace(session, state=BuyerSessionState.CANCELLED)
    assert map_buyer_session(early) == (ParentLifecycle.DELETED, BookingTaskState.CANCELLED)
    _service, facade = _service_at("dispatched")
    session = facade.lookup_session(intent_id())
    assert session is not None
    late = replace(session, state=BuyerSessionState.CANCELLED)
    assert map_buyer_session(late) == (ParentLifecycle.CANCELLED, BookingTaskState.CANCELLED)
    superseded = replace(session, state=BuyerSessionState.SUPERSEDED)
    assert map_buyer_session(superseded) == (
        ParentLifecycle.CANCELLED,
        BookingTaskState.SUPERSEDED,
    )
    service = OrchestrationService(facade)
    facade._sessions.save(late)
    assert service.get_intent(PI)["state"] == "cancelled"
    facade._sessions.save(early)
    assert service.get_intent(PI)["state"] == "deleted"


def test_a4_is_not_a_booking_and_confirmation_binds_requirement() -> None:
    service, facade = _service_at("created")
    created_task = service.get_task(PI, BT)
    assert created_task["state"] == "a1_review"
    assert created_task["requirementVersion"] == 1
    assert created_task["domain"] == "parking"
    assert created_task["inventory"] == "not_held"
    assert created_task["transactionResult"] == "simulated"
    service, _facade = _service_at("authorized")
    parent = service.get_intent(PI)
    task = service.get_task(PI, BT)
    ledger = service.get_ledger(PI)
    assert parent["state"] == "completed_simulated"
    assert task["state"] == "authorized_simulated"
    assert task["transactionResult"] == "authorized_simulated"
    assert task["state"] != "confirmed_booking"
    assert ledger["rows"][0]["confirmedBookingMinor"] == 0
    assert ledger["rows"][0]["authorizedSimulatedMinor"] == 14800


def test_contract_shaped_documents_and_no_score_micros() -> None:
    service, _facade = _service_at("dispatched")
    intent = service.get_intent(PI)
    plan = service.get_plan(PI)
    ledger = service.get_ledger(PI)
    task = service.get_task(PI, BT)
    assert intent["intentId"] == OI
    assert intent["planId"] == "pl_" + BODY
    assert intent["ledgerId"] == "ld_" + BODY
    assert intent["simulation"] is True
    assert intent["durability"] == "unsupported"
    assert intent["objective"] == "Airport parking JFK"
    assert "conversationId" not in intent
    assert plan["taskIds"] == [BT]
    assert plan["combinedRecommendationsEligible"] is False
    assert task["purchaseIntentId"] == PI
    for document in (intent, plan, ledger, task):
        assert "scoreMicros" not in document
        assert "score_micros" not in document


def test_supplier_bound_fields_exclude_parent_and_siblings() -> None:
    service, _facade = _service_at("dispatched")
    task = service.get_task(PI, BT)
    bound = supplier_bound_fields(task)
    assert bound["taskId"] == BT
    assert bound["domain"] == "parking"
    assert "intentId" not in bound
    assert "purchaseIntentId" not in bound
    assert "conversationId" not in bound
    assert "planId" not in bound
    assert "offers" not in bound
    assert "preferences" not in bound
    assert "buyerToken" not in bound
    leaked = {
        "intentId": OI,
        "conversationId": "cv_1",
        "planId": "pl_" + BODY,
        "siblings": [BT],
        "preferences": {"covered": "preferred"},
        "buyerToken": "bs_" + BODY,
        "taskId": BT,
        "domain": "parking",
        "state": "offers_ready",
        "simulation": True,
    }
    isolated = supplier_bound_fields(leaked)
    assert isolated == {
        "taskId": BT,
        "domain": "parking",
        "state": "offers_ready",
        "simulation": True,
    }


def test_sibling_plan_order_and_isolation() -> None:
    other = "bt_01k2m3n4p5q6r7s8t9v0w1x2y4"
    first = project_plan(
        OI,
        "pl_" + BODY,
        (
            PlanTaskInput(BT, TaskMembership.ACCEPTED, BookingTaskState.OFFERS_READY),
            PlanTaskInput(other, TaskMembership.ACCEPTED, BookingTaskState.A1_REVIEW),
        ),
    )
    shuffled_input = project_plan(
        OI,
        "pl_" + BODY,
        (
            PlanTaskInput(other, TaskMembership.ACCEPTED, BookingTaskState.A1_REVIEW),
            PlanTaskInput(BT, TaskMembership.ACCEPTED, BookingTaskState.OFFERS_READY),
        ),
    )
    assert first["taskIds"] == [BT, other]
    assert shuffled_input["taskIds"] == [other, BT]
    assert first["combinedRecommendationsEligible"] is False
    ready = project_plan(
        OI,
        "pl_" + BODY,
        (
            PlanTaskInput(BT, TaskMembership.ACCEPTED, BookingTaskState.OFFERS_READY),
            PlanTaskInput(other, TaskMembership.ACCEPTED, BookingTaskState.OFFERS_EXPIRING),
        ),
    )
    assert ready["combinedRecommendationsEligible"] is True
    mutated_a = project_plan(
        OI,
        "pl_" + BODY,
        (
            PlanTaskInput(BT, TaskMembership.ACCEPTED, BookingTaskState.AUTHORIZED_SIMULATED),
            PlanTaskInput(other, TaskMembership.ACCEPTED, BookingTaskState.A1_REVIEW),
        ),
    )
    assert mutated_a["taskIds"][1] == other
    assert mutated_a["combinedRecommendationsEligible"] is False


def test_parking_golden_path_mutations_unchanged() -> None:
    facade = build_facade()
    created = facade.create_purchase_intent(jfk_payload())
    assert created.state is BuyerSessionState.AWAITING_REQUIREMENT_CONFIRMATION
    confirmed = facade.confirm_requirement(intent_id(), governance(A1_ID))
    assert confirmed.state is BuyerSessionState.AWAITING_DISPATCH_APPROVAL
    dispatched = facade.approve_and_dispatch(intent_id(), governance(A2_ID))
    assert dispatched.state is BuyerSessionState.OFFERS_RANKED
    winner = next(item for item in dispatched.offers if item.recommended)
    accepted = facade.accept_recommended_or_selected_offer(
        intent_id(), accept_command(winner.offer_id)
    )
    assert accepted.state is BuyerSessionState.ACCEPTANCE_RECORDED
    authorized = facade.authorize_simulated_transaction(
        intent_id(),
        authorize_command(
            acceptance_id=accepted.acceptance.acceptance_id,
            amount_minor=winner.total_minor,
            supplier_token=winner.supplier_token,
        ),
    )
    assert authorized.state is BuyerSessionState.TRANSACTION_AUTHORIZED_SIMULATED
    assert authorized.transaction is not None
    assert authorized.transaction.mode == "SIMULATED"
