from __future__ import annotations

import pytest
from wp04_helpers import A1_ID, A2_ID
from wp06_fakes import (
    accept_command,
    authorize_command,
    build_memory,
    governance,
    intent_id,
    jfk_payload,
)

from itaa_application.errors import ApplicationError
from itaa_application.local_memory import MemoryInspection
from itaa_application.session_models import BuyerSessionState
from itaa_policy.idempotency import IdempotencyState

A4_POINTS = (
    "a4.after_approval",
    "a4.after_idempotency",
    "a4.after_tx_requested",
    "a4.after_audit_requested",
    "a4.after_tx_required",
    "a4.after_audit_required",
    "a4.after_tx_authorized",
    "a4.after_audit_authorized",
    "a4.before_session_save",
)


def _assert_unchanged(before: MemoryInspection, after: MemoryInspection) -> None:
    assert after.session_states == before.session_states
    assert after.authorization_result_refs == before.authorization_result_refs
    assert after.approval_ids == before.approval_ids
    assert after.idempotency_states == before.idempotency_states
    assert after.idempotency_result_refs == before.idempotency_result_refs
    assert after.audit_event_ids == before.audit_event_ids
    assert after.capacities == before.capacities
    completed = {
        key
        for key, state in after.idempotency_states.items()
        if state is IdempotencyState.COMPLETED
    }
    for key in completed:
        intent = next(iter(after.session_states))
        assert after.session_states[intent] is BuyerSessionState.TRANSACTION_AUTHORIZED_SIMULATED
        assert after.authorization_result_refs[intent] == after.idempotency_result_refs[key]


def _created():
    facade, memory, faults = build_memory()
    facade.create_purchase_intent(jfk_payload())
    return facade, memory, faults


def _confirmed():
    facade, memory, faults = _created()
    facade.confirm_requirement(intent_id(), governance(A1_ID))
    return facade, memory, faults


def _dispatched():
    facade, memory, faults = _confirmed()
    snapshot = facade.approve_and_dispatch(intent_id(), governance(A2_ID))
    return facade, memory, faults, snapshot


def _accepted():
    facade, memory, faults, snapshot = _dispatched()
    accepted = facade.accept_recommended_or_selected_offer(
        intent_id(), accept_command(snapshot.recommended_offer_id or "")
    )
    winner = next(item for item in snapshot.offers if item.recommended)
    return facade, memory, faults, accepted, winner


def test_a1_failure_after_approval_and_audit_rolls_back_all_stores() -> None:
    facade, memory, faults = _created()
    before = memory.inspect()
    faults.fail_at("a1.after_approval_and_audit")
    with pytest.raises(ApplicationError, match="internal: injected_fault"):
        facade.confirm_requirement(intent_id(), governance(A1_ID))
    after = memory.inspect()
    _assert_unchanged(before, after)
    assert after.session_states[intent_id().to_primitive()] is (
        BuyerSessionState.AWAITING_REQUIREMENT_CONFIRMATION
    )
    retry = facade.confirm_requirement(intent_id(), governance(A1_ID))
    assert retry.state is BuyerSessionState.AWAITING_DISPATCH_APPROVAL
    committed = memory.inspect()
    assert A1_ID.to_primitive() in committed.approval_ids
    assert len(committed.audit_event_ids) > len(before.audit_event_ids)


def test_a2_failure_after_approval_and_after_collection_restores_capacity() -> None:
    facade, memory, faults = _confirmed()
    before = memory.inspect()
    assert before.capacities
    faults.fail_at("a2.after_approval_and_audit")
    with pytest.raises(ApplicationError, match="internal: injected_fault"):
        facade.approve_and_dispatch(intent_id(), governance(A2_ID))
    _assert_unchanged(before, memory.inspect())
    faults.fail_at("a2.after_collection_and_capacity")
    with pytest.raises(ApplicationError, match="internal: injected_fault"):
        facade.approve_and_dispatch(intent_id(), governance(A2_ID))
    rolled = memory.inspect()
    _assert_unchanged(before, rolled)
    retry = facade.approve_and_dispatch(intent_id(), governance(A2_ID))
    assert retry.state is BuyerSessionState.OFFERS_RANKED
    after = memory.inspect()
    assert after.capacities != before.capacities
    assert all(
        after.capacities[token] == before.capacities[token] - 1 for token in before.capacities
    )


def test_a3_failure_after_audit_leaves_ranked_session() -> None:
    facade, memory, faults, snapshot = _dispatched()
    before = memory.inspect()
    faults.fail_at("a3.after_audit")
    with pytest.raises(ApplicationError, match="internal: injected_fault"):
        facade.accept_recommended_or_selected_offer(
            intent_id(), accept_command(snapshot.recommended_offer_id or "")
        )
    _assert_unchanged(before, memory.inspect())
    assert memory.inspect().session_states[intent_id().to_primitive()] is (
        BuyerSessionState.OFFERS_RANKED
    )
    retry = facade.accept_recommended_or_selected_offer(
        intent_id(), accept_command(snapshot.recommended_offer_id or "")
    )
    assert retry.state is BuyerSessionState.ACCEPTANCE_RECORDED


@pytest.mark.parametrize("point", A4_POINTS)
def test_a4_failure_points_never_poison_idempotency(point: str) -> None:
    facade, memory, faults, accepted, winner = _accepted()
    before = memory.inspect()
    command = authorize_command(
        acceptance_id=accepted.acceptance.acceptance_id if accepted.acceptance else "",
        amount_minor=winner.total_minor,
        supplier_token=winner.supplier_token,
    )
    faults.fail_at(point)
    with pytest.raises(ApplicationError, match="internal: injected_fault"):
        facade.authorize_simulated_transaction(intent_id(), command)
    after = memory.inspect()
    _assert_unchanged(before, after)
    intent_key = intent_id().to_primitive()
    assert after.session_states[intent_key] is BuyerSessionState.ACCEPTANCE_RECORDED
    assert after.authorization_result_refs[intent_key] is None
    assert IdempotencyState.COMPLETED not in after.idempotency_states.values()
    retry = facade.authorize_simulated_transaction(intent_id(), command)
    assert retry.state is BuyerSessionState.TRANSACTION_AUTHORIZED_SIMULATED
    assert retry.transaction is not None
    assert retry.transaction.result_ref is not None
    final = memory.inspect()
    assert final.session_states[intent_key] is BuyerSessionState.TRANSACTION_AUTHORIZED_SIMULATED
    assert final.authorization_result_refs[intent_key] == retry.transaction.result_ref
    completed = [
        key
        for key, state in final.idempotency_states.items()
        if state is IdempotencyState.COMPLETED
    ]
    assert len(completed) == 1
    replay = facade.authorize_simulated_transaction(intent_id(), command)
    assert replay.transaction is not None
    assert replay.transaction.result_ref == retry.transaction.result_ref
