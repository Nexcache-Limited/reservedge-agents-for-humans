from __future__ import annotations

from wp04_helpers import A1_ID, A2_ID
from wp06_fakes import JFK, build_memory, governance, intent_id

from itaa_application.golden_path import _progress_terminal
from itaa_application.local_progress import InMemoryProgressBus
from itaa_application.progress_events import ProgressEventKind
from itaa_application.session_models import BuyerSessionState
from itaa_application.supplier_port import TerminalKind


def test_every_supplier_terminal_kind_has_a_closed_progress_mapping() -> None:
    expected = {
        TerminalKind.OFFER: ProgressEventKind.SUPPLIER_OFFER_RECEIVED,
        TerminalKind.DECLINED: ProgressEventKind.SUPPLIER_DECLINED,
        TerminalKind.TIMED_OUT: ProgressEventKind.SUPPLIER_TIMED_OUT,
        TerminalKind.LATE: ProgressEventKind.SUPPLIER_LATE,
        TerminalKind.INVALID: ProgressEventKind.SUPPLIER_INVALID,
        TerminalKind.FAILED: ProgressEventKind.SUPPLIER_FAILED,
        TerminalKind.DENIED: ProgressEventKind.SUPPLIER_FAILED,
    }
    for kind, progress_kind in expected.items():
        mapped, status = _progress_terminal(kind)
        assert mapped is progress_kind
        if kind is TerminalKind.DENIED:
            assert status == "dispatch_denied"
        if kind is TerminalKind.FAILED:
            assert status == "closed"


def test_dispatch_emits_ordered_progress_without_changing_ranking() -> None:
    facade, _uow, _faults = build_memory()
    bus = InMemoryProgressBus()
    facade._progress = bus
    created = facade.create_purchase_intent(dict(JFK))
    facade.confirm_requirement(intent_id(), governance(A1_ID))
    snapshot = facade.approve_and_dispatch(intent_id(), governance(A2_ID))
    assert snapshot.state is BuyerSessionState.OFFERS_RANKED
    by_id = {item.offer_id: item for item in snapshot.offers}
    assert by_id["of_01k2m3n4p5q6r7s8t9v0w1x2a2"].score_micros == 671_000
    assert by_id["of_01k2m3n4p5q6r7s8t9v0w1x2a1"].score_micros == 660_000
    assert by_id["of_01k2m3n4p5q6r7s8t9v0w1x2a3"].score_micros == 535_000
    assert snapshot.downside is not None
    assert snapshot.downside.delta == 2900
    kinds = [item.kind for item in bus.events_after(created.intent_id, None)]
    assert kinds[0] is ProgressEventKind.SOLICITATION_PREPARING
    assert kinds[1] is ProgressEventKind.SOLICITATION_DISPATCHED
    assert kinds[2:5] == [ProgressEventKind.SUPPLIER_WAITING] * 3
    assert ProgressEventKind.SUPPLIER_OFFER_RECEIVED in kinds
    assert kinds[-4:] == [
        ProgressEventKind.VALIDATION_COMPLETED,
        ProgressEventKind.RANKING_COMPLETED,
        ProgressEventKind.RECOMMENDATION_READY,
        ProgressEventKind.STREAM_COMPLETED,
    ]
    tokens = [
        item.supplier_token
        for item in bus.events_after(created.intent_id, None)
        if item.kind is ProgressEventKind.SUPPLIER_WAITING
    ]
    assert len(set(tokens)) == 3
    for event in bus.events_after(created.intent_id, None):
        public = event.to_public()
        assert public["generationId"].startswith("pg_")
        assert "totalMinor" not in public
        assert "scoreMicros" not in public
