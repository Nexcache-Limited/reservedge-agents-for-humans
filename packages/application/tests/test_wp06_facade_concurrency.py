from __future__ import annotations

from threading import Barrier, Thread

from wp04_helpers import A1_ID, A2_ID, OCCURRED_AT
from wp06_fakes import (
    accept_command,
    authorize_command,
    build_memory,
    governance,
    intent_id,
    jfk_payload,
)

from itaa_application.errors import ApplicationError
from itaa_application.session_models import BuyerSessionState
from itaa_application.supplier_port import FrozenClock
from itaa_policy.idempotency import IdempotencyState


def _accepted_stack():
    facade, memory, _faults = build_memory(clock=FrozenClock(OCCURRED_AT))
    facade.create_purchase_intent(jfk_payload())
    facade.confirm_requirement(intent_id(), governance(A1_ID))
    dispatched = facade.approve_and_dispatch(intent_id(), governance(A2_ID))
    accepted = facade.accept_recommended_or_selected_offer(
        intent_id(), accept_command(dispatched.recommended_offer_id or "")
    )
    winner = next(item for item in dispatched.offers if item.recommended)
    return facade, memory, accepted, winner


def _run_threads(workers: list[object]) -> None:
    barrier = Barrier(len(workers))

    def wrap(fn: object) -> None:
        barrier.wait()
        fn()  # type: ignore[operator]

    threads = [Thread(target=wrap, args=(worker,)) for worker in workers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


def test_concurrent_authorize_same_key_executes_once() -> None:
    facade, memory, accepted, winner = _accepted_stack()
    command = authorize_command(
        acceptance_id=accepted.acceptance.acceptance_id if accepted.acceptance else "",
        amount_minor=winner.total_minor,
        supplier_token=winner.supplier_token,
    )
    outcomes: list[object] = []

    def worker() -> None:
        try:
            outcomes.append(facade.authorize_simulated_transaction(intent_id(), command))
        except ApplicationError as exc:
            outcomes.append(exc)

    _run_threads([worker, worker])
    snapshots = [item for item in outcomes if not isinstance(item, ApplicationError)]
    errors = [item for item in outcomes if isinstance(item, ApplicationError)]
    assert len(snapshots) >= 1
    refs = {
        item.transaction.result_ref
        for item in snapshots
        if hasattr(item, "transaction") and item.transaction is not None
    }
    assert len(refs) == 1
    inspect = memory.inspect()
    intent_key = intent_id().to_primitive()
    assert inspect.session_states[intent_key] is BuyerSessionState.TRANSACTION_AUTHORIZED_SIMULATED
    completed = [
        key
        for key, state in inspect.idempotency_states.items()
        if state is IdempotencyState.COMPLETED
    ]
    assert len(completed) == 1
    assert inspect.authorization_result_refs[intent_key] == next(iter(refs))
    for error in errors:
        assert error.code in {"illegal_state", "in_progress", "request_mismatch"}


def test_concurrent_accept_cannot_commit_conflicting_offers() -> None:
    facade, memory, _faults = build_memory(clock=FrozenClock(OCCURRED_AT))
    facade.create_purchase_intent(jfk_payload())
    facade.confirm_requirement(intent_id(), governance(A1_ID))
    dispatched = facade.approve_and_dispatch(intent_id(), governance(A2_ID))
    first = dispatched.offers[0].offer_id
    second = dispatched.offers[1].offer_id
    outcomes: list[object] = []

    def accept(offer_id: str) -> None:
        try:
            outcomes.append(
                facade.accept_recommended_or_selected_offer(intent_id(), accept_command(offer_id))
            )
        except ApplicationError as exc:
            outcomes.append(exc)

    _run_threads([lambda: accept(first), lambda: accept(second)])
    snapshots = [item for item in outcomes if not isinstance(item, ApplicationError)]
    errors = [item for item in outcomes if isinstance(item, ApplicationError)]
    assert len(snapshots) == 1
    assert len(errors) == 1
    assert errors[0].code in {"illegal_state", "approval_reused"}
    inspect = memory.inspect()
    assert (
        inspect.session_states[intent_id().to_primitive()] is BuyerSessionState.ACCEPTANCE_RECORDED
    )
    assert snapshots[0].acceptance is not None
