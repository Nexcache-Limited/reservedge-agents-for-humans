"""COMP-G1-04 application lifecycle: cancel, replace, delete, isolation, races."""

from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from threading import Barrier, Thread

from wp04_helpers import A1_ID, A2_ID, A3_ID, OCCURRED_AT
from wp06_fakes import (
    accept_command,
    authorize_command,
    build_memory,
    governance,
    jfk_payload,
)

from itaa_application.errors import ApplicationError
from itaa_application.session_models import BuyerSessionState
from itaa_application.supplier_port import FrozenClock
from itaa_domain.identifiers import IntentId
from itaa_domain.purchase_intent import PurchaseIntentState

PORTFOLIO_A = "pf_01k2m3n4p5q6r7s8t9v0w1x2aa"
PORTFOLIO_B = "pf_01k2m3n4p5q6r7s8t9v0w1x2ab"
REPLACE_KEY = "ik_01k2m3n4p5q6r7s8t9v0w1x2k1"
REPLACE_KEY_B = "ik_01k2m3n4p5q6r7s8t9v0w1x2k2"


def _payload(suffix: str) -> dict[str, object]:
    payload = jfk_payload()
    payload["intentId"] = f"pi_01k2m3n4p5q6r7s8t9v0w1x2{suffix}"
    payload["buyerToken"] = f"bs_01k2m3n4p5q6r7s8t9v0w1x2{suffix}"
    return payload


def _intent(suffix: str) -> IntentId:
    return IntentId(f"pi_01k2m3n4p5q6r7s8t9v0w1x2{suffix}")


def test_ten_intents_coexist_and_eleventh_does_not_mutate() -> None:
    facade, _memory, _faults = build_memory(clock=FrozenClock(OCCURRED_AT))
    snapshots = []
    for index in range(10):
        suffix = f"a{index}"
        snapshots.append(facade.create_purchase_intent(_payload(suffix), portfolio_id=PORTFOLIO_A))
    listed = facade.list_buyer_snapshots(PORTFOLIO_A)
    assert len(listed) == 10
    first_ids = {item.intent_id for item in listed}
    facade.create_purchase_intent(_payload("b0"), portfolio_id=PORTFOLIO_A)
    after = facade.list_buyer_snapshots(PORTFOLIO_A)
    assert len(after) == 11
    assert first_ids <= {item.intent_id for item in after}
    assert snapshots[0].state is BuyerSessionState.AWAITING_REQUIREMENT_CONFIRMATION


def test_foreign_portfolio_cannot_list_or_mutate() -> None:
    facade, _memory, _faults = build_memory(clock=FrozenClock(OCCURRED_AT))
    created = facade.create_purchase_intent(_payload("c1"), portfolio_id=PORTFOLIO_A)
    assert facade.list_buyer_snapshots(PORTFOLIO_B) == ()
    try:
        facade.cancel_purchase_intent(IntentId(created.intent_id), PORTFOLIO_B, governance(A1_ID))
    except ApplicationError as exc:
        assert exc.field == "intentId"
        assert exc.code == "unknown_resource"
        assert created.intent_id not in exc.field
    else:
        raise AssertionError("foreign cancel")
    assert facade.get_buyer_snapshot(IntentId(created.intent_id)).state is (
        BuyerSessionState.AWAITING_REQUIREMENT_CONFIRMATION
    )


def test_delete_only_clean_draft() -> None:
    facade, _memory, _faults = build_memory(clock=FrozenClock(OCCURRED_AT))
    created = facade.create_purchase_intent(_payload("d1"), portfolio_id=PORTFOLIO_A)
    facade.delete_undisclosed_draft(IntentId(created.intent_id), PORTFOLIO_A)
    assert facade.list_buyer_snapshots(PORTFOLIO_A) == ()
    confirmed = facade.create_purchase_intent(_payload("d2"), portfolio_id=PORTFOLIO_A)
    facade.confirm_requirement(IntentId(confirmed.intent_id), governance(A1_ID))
    try:
        facade.delete_undisclosed_draft(IntentId(confirmed.intent_id), PORTFOLIO_A)
    except ApplicationError as exc:
        assert exc.code == "conflict"
    else:
        raise AssertionError("delete after A1")


def test_cancel_after_authorization_refused() -> None:
    facade, memory, _faults = build_memory(clock=FrozenClock(OCCURRED_AT))
    facade.create_purchase_intent(_payload("e1"), portfolio_id=PORTFOLIO_A)
    intent = _intent("e1")
    facade.confirm_requirement(intent, governance(A1_ID))
    dispatched = facade.approve_and_dispatch(intent, governance(A2_ID))
    accepted = facade.accept_recommended_or_selected_offer(
        intent, accept_command(dispatched.recommended_offer_id or "")
    )
    winner = next(item for item in dispatched.offers if item.recommended)
    facade.authorize_simulated_transaction(
        intent,
        authorize_command(
            acceptance_id=accepted.acceptance.acceptance_id if accepted.acceptance else "",
            amount_minor=winner.total_minor,
            supplier_token=winner.supplier_token,
        ),
    )
    before = memory.inspect().session_states[intent.to_primitive()]
    try:
        facade.cancel_purchase_intent(intent, PORTFOLIO_A, governance(A1_ID))
    except ApplicationError as exc:
        assert exc.code == "illegal_state"
    else:
        raise AssertionError("cancel completed")
    assert memory.inspect().session_states[intent.to_primitive()] is before


def test_cancelled_cannot_dispatch_accept_or_authorize() -> None:
    facade, _memory, _faults = build_memory(clock=FrozenClock(OCCURRED_AT))
    facade.create_purchase_intent(_payload("f1"), portfolio_id=PORTFOLIO_A)
    intent = _intent("f1")
    facade.confirm_requirement(intent, governance(A1_ID))
    facade.cancel_purchase_intent(intent, PORTFOLIO_A, governance(A1_ID))
    for fn in (
        lambda: facade.approve_and_dispatch(intent, governance(A2_ID)),
        lambda: facade.accept_recommended_or_selected_offer(
            intent, accept_command("of_01k2m3n4p5q6r7s8t9v0w1x2a2")
        ),
        lambda: facade.authorize_simulated_transaction(
            intent,
            authorize_command(
                acceptance_id="ac_01k2m3n4p5q6r7s8t9v0w1x2d1",
                amount_minor=14800,
                supplier_token="sp_01k2m3n4p5q6r7s8t9v0w1x2s2",
            ),
        ),
    ):
        try:
            fn()
        except ApplicationError as exc:
            assert exc.code in {"illegal_state", "unknown_resource", "required"}
        else:
            raise AssertionError("post-cancel mutation")


def test_cancel_revokes_a2_and_a3() -> None:
    facade, memory, _faults = build_memory(clock=FrozenClock(OCCURRED_AT))
    facade.create_purchase_intent(_payload("g1"), portfolio_id=PORTFOLIO_A)
    intent = _intent("g1")
    facade.confirm_requirement(intent, governance(A1_ID))
    dispatched = facade.approve_and_dispatch(intent, governance(A2_ID))
    facade.accept_recommended_or_selected_offer(
        intent, accept_command(dispatched.recommended_offer_id or "")
    )
    facade.cancel_purchase_intent(intent, PORTFOLIO_A, governance(A1_ID))
    assert facade.get_buyer_snapshot(intent).state is BuyerSessionState.CANCELLED
    for approval in (A2_ID, A3_ID):
        assert memory.approvals.resolve(approval).revoked is True
    assert memory.approvals.resolve(A1_ID).revoked is True


def test_replace_after_dispatch_is_superseded_and_mints_new_ids() -> None:
    facade, _memory, _faults = build_memory(clock=FrozenClock(OCCURRED_AT))
    original_payload = _payload("h1")
    facade.create_purchase_intent(original_payload, portfolio_id=PORTFOLIO_A)
    intent = _intent("h1")
    facade.confirm_requirement(intent, governance(A1_ID))
    dispatched = facade.approve_and_dispatch(intent, governance(A2_ID))
    offer_ids = {item.offer_id for item in dispatched.offers}
    result = facade.replace_purchase_intent(intent, PORTFOLIO_A, governance(A1_ID), REPLACE_KEY)
    assert result.previous.state is BuyerSessionState.SUPERSEDED
    assert result.draft.state is BuyerSessionState.AWAITING_REQUIREMENT_CONFIRMATION
    assert result.draft.intent_id != result.previous.intent_id
    assert result.draft.replaces_intent_id == result.previous.intent_id
    assert result.previous.replaced_by_intent_id == result.draft.intent_id
    assert not result.draft.offers
    assert offer_ids.isdisjoint({item.offer_id for item in result.draft.offers})
    replayed = facade.replace_purchase_intent(intent, PORTFOLIO_A, governance(A1_ID), REPLACE_KEY)
    assert replayed.draft.intent_id == result.draft.intent_id
    original_session = facade._sessions.get(intent)
    draft_session = facade._sessions.get(IntentId(result.draft.intent_id))
    assert original_session is not None and draft_session is not None
    assert original_session.requirement.requirement_id != draft_session.requirement.requirement_id
    assert original_session.purchase_intent.buyer_token != draft_session.purchase_intent.buyer_token
    assert draft_session.used_approval_ids == frozenset()
    assert draft_session.collection is None
    assert draft_session.mapped_offers == ()
    try:
        facade.replace_purchase_intent(intent, PORTFOLIO_A, governance(A1_ID), REPLACE_KEY_B)
    except ApplicationError as exc:
        assert exc.code in {"illegal_state", "request_mismatch"}
    else:
        raise AssertionError("conflicting replace")


def test_replace_replay_one_thousand_times() -> None:
    facade, _memory, _faults = build_memory(clock=FrozenClock(OCCURRED_AT))
    facade.create_purchase_intent(_payload("n1"), portfolio_id=PORTFOLIO_A)
    intent = _intent("n1")
    first = facade.replace_purchase_intent(intent, PORTFOLIO_A, governance(A1_ID), REPLACE_KEY)
    for _ in range(1000):
        replayed = facade.replace_purchase_intent(
            intent, PORTFOLIO_A, governance(A1_ID), REPLACE_KEY
        )
        assert replayed.draft.intent_id == first.draft.intent_id
    owned = facade.list_buyer_snapshots(PORTFOLIO_A)
    drafts = [
        item for item in owned if item.state is BuyerSessionState.AWAITING_REQUIREMENT_CONFIRMATION
    ]
    assert len(drafts) == 1


def test_save_does_not_change_domain_or_expiry() -> None:
    facade, _memory, _faults = build_memory(clock=FrozenClock(OCCURRED_AT))
    created = facade.create_purchase_intent(_payload("j1"), portfolio_id=PORTFOLIO_A)
    saved = facade.set_saved(IntentId(created.intent_id), PORTFOLIO_A, True)
    assert saved.saved is True
    assert saved.state is created.state
    assert saved.expires_at == created.expires_at
    session = facade._sessions.get(IntentId(created.intent_id))
    assert session is not None
    assert session.purchase_intent.state is PurchaseIntentState.DRAFT
    assert session.purchase_intent.expires_at == session.purchase_intent.expires_at


def test_locked_jfk_scores_unchanged_after_portfolio_create() -> None:
    facade, _memory, _faults = build_memory(clock=FrozenClock(OCCURRED_AT))
    facade.create_purchase_intent(jfk_payload(), portfolio_id=PORTFOLIO_A)
    facade.confirm_requirement(IntentId(str(jfk_payload()["intentId"])), governance(A1_ID))
    dispatched = facade.approve_and_dispatch(
        IntentId(str(jfk_payload()["intentId"])), governance(A2_ID)
    )
    by_name = {item.supplier_token: item for item in dispatched.offers}
    scores = sorted(item.score_micros for item in dispatched.offers)
    assert scores == [535000, 660000, 671000]
    recommended = next(item for item in dispatched.offers if item.recommended)
    assert recommended.score_micros == 671000
    del by_name


def test_cancel_versus_dispatch_one_winner() -> None:
    facade, memory, _faults = build_memory(clock=FrozenClock(OCCURRED_AT))
    facade.create_purchase_intent(_payload("k1"), portfolio_id=PORTFOLIO_A)
    intent = _intent("k1")
    facade.confirm_requirement(intent, governance(A1_ID))
    outcomes: list[object] = []
    barrier = Barrier(2)

    def cancel() -> None:
        barrier.wait()
        try:
            outcomes.append(facade.cancel_purchase_intent(intent, PORTFOLIO_A, governance(A1_ID)))
        except ApplicationError as exc:
            outcomes.append(exc)

    def dispatch() -> None:
        barrier.wait()
        try:
            outcomes.append(facade.approve_and_dispatch(intent, governance(A2_ID)))
        except ApplicationError as exc:
            outcomes.append(exc)

    threads = [Thread(target=cancel), Thread(target=dispatch)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    states = memory.inspect().session_states[intent.to_primitive()]
    assert states is BuyerSessionState.CANCELLED
    cancelled = facade.get_buyer_snapshot(intent)
    assert cancelled.state is BuyerSessionState.CANCELLED
    assert any(not isinstance(item, ApplicationError) for item in outcomes)


def test_injected_fault_rolls_back_cancel() -> None:
    facade, memory, faults = build_memory(clock=FrozenClock(OCCURRED_AT))
    facade.create_purchase_intent(_payload("m1"), portfolio_id=PORTFOLIO_A)
    intent = _intent("m1")
    facade.confirm_requirement(intent, governance(A1_ID))
    before = deepcopy(memory.inspect().session_states)
    faults.fail_at("cancel.before_save")
    try:
        facade.cancel_purchase_intent(intent, PORTFOLIO_A, governance(A1_ID))
    except ApplicationError as exc:
        assert exc.code == "injected_fault"
    else:
        raise AssertionError("fault")
    assert memory.inspect().session_states == before
    assert memory.approvals.resolve(A1_ID).revoked is False


def test_cancel_versus_accept_session_ends_cancelled() -> None:
    facade, memory, _faults = build_memory(clock=FrozenClock(OCCURRED_AT))
    facade.create_purchase_intent(_payload("p1"), portfolio_id=PORTFOLIO_A)
    intent = _intent("p1")
    facade.confirm_requirement(intent, governance(A1_ID))
    dispatched = facade.approve_and_dispatch(intent, governance(A2_ID))
    offer_id = dispatched.recommended_offer_id or ""
    outcomes: list[object] = []
    barrier = Barrier(2)

    def cancel() -> None:
        barrier.wait()
        try:
            outcomes.append(facade.cancel_purchase_intent(intent, PORTFOLIO_A, governance(A1_ID)))
        except ApplicationError as exc:
            outcomes.append(exc)

    def accept() -> None:
        barrier.wait()
        try:
            outcomes.append(
                facade.accept_recommended_or_selected_offer(intent, accept_command(offer_id))
            )
        except ApplicationError as exc:
            outcomes.append(exc)

    threads = [Thread(target=cancel), Thread(target=accept)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert memory.inspect().session_states[intent.to_primitive()] is BuyerSessionState.CANCELLED
    assert any(not isinstance(item, ApplicationError) for item in outcomes)


def test_cancel_versus_authorize_one_terminal() -> None:
    facade, memory, _faults = build_memory(clock=FrozenClock(OCCURRED_AT))
    facade.create_purchase_intent(_payload("q1"), portfolio_id=PORTFOLIO_A)
    intent = _intent("q1")
    facade.confirm_requirement(intent, governance(A1_ID))
    dispatched = facade.approve_and_dispatch(intent, governance(A2_ID))
    accepted = facade.accept_recommended_or_selected_offer(
        intent, accept_command(dispatched.recommended_offer_id or "")
    )
    winner = next(item for item in dispatched.offers if item.recommended)
    outcomes: list[object] = []
    barrier = Barrier(2)

    def cancel() -> None:
        barrier.wait()
        try:
            outcomes.append(facade.cancel_purchase_intent(intent, PORTFOLIO_A, governance(A1_ID)))
        except ApplicationError as exc:
            outcomes.append(exc)

    def authorize() -> None:
        barrier.wait()
        try:
            outcomes.append(
                facade.authorize_simulated_transaction(
                    intent,
                    authorize_command(
                        acceptance_id=accepted.acceptance.acceptance_id
                        if accepted.acceptance
                        else "",
                        amount_minor=winner.total_minor,
                        supplier_token=winner.supplier_token,
                    ),
                )
            )
        except ApplicationError as exc:
            outcomes.append(exc)

    threads = [Thread(target=cancel), Thread(target=authorize)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    final = memory.inspect().session_states[intent.to_primitive()]
    assert final in {
        BuyerSessionState.CANCELLED,
        BuyerSessionState.TRANSACTION_AUTHORIZED_SIMULATED,
    }
    successes = [item for item in outcomes if not isinstance(item, ApplicationError)]
    errors = [item for item in outcomes if isinstance(item, ApplicationError)]
    assert len(successes) == 1
    assert len(errors) == 1


def test_delete_refused_for_disclosed_cancelled_and_completed() -> None:
    disclosed_facade, _dmem, _df = build_memory(clock=FrozenClock(OCCURRED_AT))
    disclosed = disclosed_facade.create_purchase_intent(_payload("r1"), portfolio_id=PORTFOLIO_A)
    intent_r = IntentId(disclosed.intent_id)
    disclosed_facade.confirm_requirement(intent_r, governance(A1_ID))
    disclosed_facade.approve_and_dispatch(intent_r, governance(A2_ID))
    try:
        disclosed_facade.delete_undisclosed_draft(intent_r, PORTFOLIO_A)
    except ApplicationError as exc:
        assert exc.code == "conflict"
    else:
        raise AssertionError("delete disclosed")

    cancelled_facade, _cmem, _cf = build_memory(clock=FrozenClock(OCCURRED_AT))
    cancelled = cancelled_facade.create_purchase_intent(_payload("x1"), portfolio_id=PORTFOLIO_A)
    intent_x = IntentId(cancelled.intent_id)
    cancelled_facade.cancel_purchase_intent(intent_x, PORTFOLIO_A, governance(A1_ID))
    try:
        cancelled_facade.delete_undisclosed_draft(intent_x, PORTFOLIO_A)
    except ApplicationError as exc:
        assert exc.code == "conflict"
    else:
        raise AssertionError("delete cancelled")

    completed_facade, _ymem, _yf = build_memory(clock=FrozenClock(OCCURRED_AT))
    completed_facade.create_purchase_intent(_payload("y1"), portfolio_id=PORTFOLIO_A)
    intent_y = _intent("y1")
    completed_facade.confirm_requirement(intent_y, governance(A1_ID))
    dispatched = completed_facade.approve_and_dispatch(intent_y, governance(A2_ID))
    accepted = completed_facade.accept_recommended_or_selected_offer(
        intent_y, accept_command(dispatched.recommended_offer_id or "")
    )
    winner = next(item for item in dispatched.offers if item.recommended)
    completed_facade.authorize_simulated_transaction(
        intent_y,
        authorize_command(
            acceptance_id=accepted.acceptance.acceptance_id if accepted.acceptance else "",
            amount_minor=winner.total_minor,
            supplier_token=winner.supplier_token,
        ),
    )
    try:
        completed_facade.delete_undisclosed_draft(intent_y, PORTFOLIO_A)
    except ApplicationError as exc:
        assert exc.code == "conflict"
    else:
        raise AssertionError("delete completed")


def test_save_does_not_extend_offer_expiry() -> None:
    clock = FrozenClock(OCCURRED_AT)
    facade, _memory, _faults = build_memory(clock=clock)
    facade.create_purchase_intent(_payload("w1"), portfolio_id=PORTFOLIO_A)
    intent = _intent("w1")
    facade.confirm_requirement(intent, governance(A1_ID))
    dispatched = facade.approve_and_dispatch(intent, governance(A2_ID))
    before = dispatched.expires_at
    saved = facade.set_saved(intent, PORTFOLIO_A, True)
    assert saved.expires_at == before
    clock.advance(timedelta(hours=25))
    try:
        facade.accept_recommended_or_selected_offer(
            intent, accept_command(dispatched.recommended_offer_id or "")
        )
    except ApplicationError as exc:
        assert exc.code == "expired"
    else:
        raise AssertionError("stale accept after expiry")


def test_errors_do_not_leak_tokens_or_intake_text() -> None:
    facade, _memory, _faults = build_memory(clock=FrozenClock(OCCURRED_AT))
    created = facade.create_purchase_intent(_payload("s1"), portfolio_id=PORTFOLIO_A)
    try:
        facade.cancel_purchase_intent(IntentId(created.intent_id), PORTFOLIO_B, governance(A1_ID))
    except ApplicationError as exc:
        rendered = f"{exc.field}:{exc.code}:{exc}"
        assert created.intent_id not in rendered
        assert PORTFOLIO_A not in rendered
        assert PORTFOLIO_B not in rendered
        assert "JFK" not in rendered
        assert "pi_" not in rendered
        assert "pf_" not in rendered
    else:
        raise AssertionError("foreign cancel")


def test_foreign_portfolio_cannot_read_activity() -> None:
    facade, _memory, _faults = build_memory(clock=FrozenClock(OCCURRED_AT))
    created = facade.create_purchase_intent(_payload("t1"), portfolio_id=PORTFOLIO_A)
    owned = facade.buyer_activity(IntentId(created.intent_id), PORTFOLIO_A)
    assert owned[0]["label"] == "Request created"
    try:
        facade.buyer_activity(IntentId(created.intent_id), PORTFOLIO_B)
    except ApplicationError as exc:
        assert exc.code == "unknown_resource"
        assert created.intent_id not in f"{exc.field}{exc.code}{exc}"
    else:
        raise AssertionError("foreign activity")


def test_injected_fault_rolls_back_replace() -> None:
    facade, memory, faults = build_memory(clock=FrozenClock(OCCURRED_AT))
    facade.create_purchase_intent(_payload("z1"), portfolio_id=PORTFOLIO_A)
    intent = _intent("z1")
    before = deepcopy(memory.inspect().session_states)
    faults.fail_at("replace.before_draft_save")
    try:
        facade.replace_purchase_intent(intent, PORTFOLIO_A, governance(A1_ID), REPLACE_KEY)
    except ApplicationError as exc:
        assert exc.code == "injected_fault"
    else:
        raise AssertionError("fault")
    assert memory.inspect().session_states == before
    assert memory.replace_log.get(PORTFOLIO_A, REPLACE_KEY) is None
