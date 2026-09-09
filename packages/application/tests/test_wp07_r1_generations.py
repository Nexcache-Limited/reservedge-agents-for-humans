from __future__ import annotations

import threading
import time
from datetime import UTC, datetime

import pytest
from wp04_helpers import A1_ID, A2_ID
from wp06_fakes import JFK, build_memory, governance, intent_id

from itaa_application.errors import ApplicationError
from itaa_application.golden_path import FaultInjector
from itaa_application.local_progress import InMemoryProgressBus
from itaa_application.progress_events import ProgressEventKind
from itaa_application.session_models import BuyerSessionState

OCCURRED = datetime(2026, 8, 20, 16, 0, tzinfo=UTC)
INTENT = "pi_01k2m3n4p5q6r7s8t9v0w1x2y3"
OTHER = "pi_01k2m3n4p5q6r7s8t9v0w1x2y4"
UNKNOWN_GENERATION = "pg_" + ("0" * 26)


def _complete(bus: InMemoryProgressBus, intent_id: str, status: str) -> None:
    bus.emit(
        intent_id=intent_id,
        kind=ProgressEventKind.STREAM_COMPLETED,
        occurred_at=OCCURRED,
        status=status,
        terminal=True,
    )


def test_successful_first_dispatch_stays_one_generation() -> None:
    facade, _uow, _faults = build_memory()
    bus = InMemoryProgressBus()
    facade._progress = bus
    created = facade.create_purchase_intent(dict(JFK))
    facade.confirm_requirement(intent_id(), governance(A1_ID))
    snapshot = facade.approve_and_dispatch(intent_id(), governance(A2_ID))
    assert snapshot.state is BuyerSessionState.OFFERS_RANKED
    by_id = {item.offer_id: item for item in snapshot.offers}
    assert by_id["of_01k2m3n4p5q6r7s8t9v0w1x2a2"].score_micros == 671_000
    assert snapshot.downside is not None
    assert snapshot.downside.delta == 2900
    generations = bus.generation_ids(created.intent_id)
    assert len(generations) == 1
    events = bus.events_after(created.intent_id, None, generations[0])
    assert events[0].kind is ProgressEventKind.SOLICITATION_PREPARING
    assert events[-1].kind is ProgressEventKind.STREAM_COMPLETED
    assert events[-1].status == "complete"
    assert all(item.generation_id == generations[0] for item in events)
    assert [item.sequence for item in events] == list(range(1, len(events) + 1))


def test_pre_progress_dispatch_failure_does_not_emit_unavailable() -> None:
    facade, _uow, _faults = build_memory()
    bus = InMemoryProgressBus()
    facade._progress = bus
    created = facade.create_purchase_intent(dict(JFK))
    key = created.intent_id
    opened = bus.watch(key)
    with pytest.raises(ApplicationError, match="state: illegal_state"):
        facade.approve_and_dispatch(intent_id(), governance(A2_ID))
    assert bus.generation_ids(key) == (opened,)
    assert bus.events_after(key, None, opened) == ()
    assert bus.has_started(key) is False
    assert list(bus.subscribe(key, None, opened)) == []
    next_generation = bus.watch(key)
    assert next_generation != opened


def test_completed_generation_does_not_count_as_started_for_next_dispatch() -> None:
    facade, _uow, _faults = build_memory()
    bus = InMemoryProgressBus()
    facade._progress = bus
    created = facade.create_purchase_intent(dict(JFK))
    key = created.intent_id
    facade.confirm_requirement(intent_id(), governance(A1_ID))
    snapshot = facade.approve_and_dispatch(intent_id(), governance(A2_ID))
    assert snapshot.state is BuyerSessionState.OFFERS_RANKED
    first = bus.generation_ids(key)
    assert len(first) == 1
    assert bus.has_started(key) is False
    with pytest.raises(ApplicationError, match="state: illegal_state"):
        facade.approve_and_dispatch(intent_id(), governance(A2_ID))
    assert bus.generation_ids(key) == first
    events = bus.events_after(key, None, first[0])
    assert events[-1].status == "complete"
    assert all(item.status != "unavailable" for item in events)


def test_failed_dispatch_retry_gets_a_new_generation() -> None:
    faults = FaultInjector()
    facade, _uow, _injector = build_memory(faults=faults)
    bus = InMemoryProgressBus()
    facade._progress = bus
    created = facade.create_purchase_intent(dict(JFK))
    key = created.intent_id
    facade.confirm_requirement(intent_id(), governance(A1_ID))
    faults.fail_at("a2.after_approval_and_audit")
    with pytest.raises(ApplicationError, match="internal: injected_fault"):
        facade.approve_and_dispatch(intent_id(), governance(A2_ID))
    first = bus.generation_ids(key)
    assert len(first) == 1
    failed = bus.events_after(key, None, first[0])
    assert failed[-1].kind is ProgressEventKind.STREAM_COMPLETED
    assert failed[-1].status == "unavailable"
    retry = facade.approve_and_dispatch(intent_id(), governance(A2_ID))
    assert retry.state is BuyerSessionState.OFFERS_RANKED
    generations = bus.generation_ids(key)
    assert len(generations) == 2
    second = generations[1]
    retry_events = bus.events_after(key, None, second)
    kinds = [item.kind for item in retry_events]
    assert kinds[0] is ProgressEventKind.SOLICITATION_PREPARING
    assert ProgressEventKind.SUPPLIER_WAITING in kinds
    assert kinds[-1] is ProgressEventKind.STREAM_COMPLETED
    assert retry_events[-1].status == "complete"
    assert all(item.status != "unavailable" for item in retry_events)
    assert all(item.generation_id == second for item in retry_events)
    replayed_failure = bus.events_after(key, None, first[0])
    assert replayed_failure[-1].status == "unavailable"
    live = list(bus.subscribe(key, None, second))
    assert live[0] is not None
    assert live[0].kind is ProgressEventKind.SOLICITATION_PREPARING
    assert not any(item is not None and item.status == "unavailable" for item in live)


def test_reconnect_within_generation_resumes_after_sequence() -> None:
    bus = InMemoryProgressBus()
    generation = bus.watch(INTENT)
    bus.emit(intent_id=INTENT, kind=ProgressEventKind.SOLICITATION_PREPARING, occurred_at=OCCURRED)
    bus.emit(intent_id=INTENT, kind=ProgressEventKind.SOLICITATION_DISPATCHED, occurred_at=OCCURRED)
    resumed = bus.events_after(INTENT, 1, generation)
    assert [item.sequence for item in resumed] == [2]
    assert all(item.generation_id == generation for item in resumed)


def test_generation_cannot_replay_another_generation() -> None:
    bus = InMemoryProgressBus()
    first = bus.watch(INTENT)
    bus.emit(intent_id=INTENT, kind=ProgressEventKind.SOLICITATION_PREPARING, occurred_at=OCCURRED)
    _complete(bus, INTENT, "unavailable")
    second = bus.watch(INTENT)
    bus.emit(intent_id=INTENT, kind=ProgressEventKind.SOLICITATION_PREPARING, occurred_at=OCCURRED)
    other_events = bus.events_after(INTENT, None, second)
    assert all(item.generation_id == second for item in other_events)
    assert all(item.status != "unavailable" for item in other_events)
    with pytest.raises(ApplicationError) as raised:
        bus.events_after(INTENT, 2, second)
    assert raised.value.field == "lastEventId"
    assert raised.value.code == "schema_invalid"
    prior = bus.events_after(INTENT, None, first)
    assert prior[-1].status == "unavailable"
    assert second != first


def test_unknown_intent_and_generation_fail_closed() -> None:
    bus = InMemoryProgressBus()
    bus.emit(intent_id=INTENT, kind=ProgressEventKind.SOLICITATION_PREPARING, occurred_at=OCCURRED)
    with pytest.raises(ApplicationError) as unknown_generation:
        bus.watch(INTENT, UNKNOWN_GENERATION)
    assert unknown_generation.value.field == "generationId"
    assert unknown_generation.value.code == "unknown_resource"
    with pytest.raises(ApplicationError) as unknown_intent:
        bus.watch(OTHER, bus.generation_ids(INTENT)[0])
    assert unknown_intent.value.field == "generationId"
    with pytest.raises(ApplicationError):
        bus.events_after(INTENT, None, UNKNOWN_GENERATION)


def test_cross_intent_generation_access_fails_closed() -> None:
    bus = InMemoryProgressBus()
    bus.emit(intent_id=INTENT, kind=ProgressEventKind.SOLICITATION_PREPARING, occurred_at=OCCURRED)
    stolen = bus.generation_ids(INTENT)[0]
    bus.emit(intent_id=OTHER, kind=ProgressEventKind.RANKING_COMPLETED, occurred_at=OCCURRED)
    with pytest.raises(ApplicationError) as raised:
        bus.events_after(OTHER, None, stolen)
    assert raised.value.code == "unknown_resource"
    assert bus.events_after(OTHER, None)[0].kind is ProgressEventKind.RANKING_COMPLETED


def test_sequential_failures_remain_bounded() -> None:
    bus = InMemoryProgressBus(max_generations=2)
    for _ in range(5):
        bus.emit(
            intent_id=INTENT, kind=ProgressEventKind.SOLICITATION_PREPARING, occurred_at=OCCURRED
        )
        _complete(bus, INTENT, "unavailable")
    remaining = bus.generation_ids(INTENT)
    assert len(remaining) == 2
    for generation_id in remaining:
        events = bus.events_after(INTENT, None, generation_id)
        assert events[-1].status == "unavailable"
        assert len(events) <= 2


def test_slow_subscriber_does_not_block_emit() -> None:
    bus = InMemoryProgressBus(heartbeat_seconds=0.05)
    generation = bus.watch(INTENT)
    started = threading.Event()
    finished = threading.Event()

    def reader() -> None:
        stream = bus.subscribe(INTENT, None, generation)
        started.set()
        for item in stream:
            if item is not None and item.terminal:
                break
            time.sleep(0.05)
        finished.set()

    worker = threading.Thread(target=reader, daemon=True)
    worker.start()
    assert started.wait(timeout=1)
    began = time.monotonic()
    bus.emit(
        intent_id=INTENT,
        kind=ProgressEventKind.SUPPLIER_WAITING,
        occurred_at=OCCURRED,
        supplier_token="sp_01k2m3n4p5q6r7s8t9v0w1x2b1",
    )
    _complete(bus, INTENT, "complete")
    elapsed = time.monotonic() - began
    assert elapsed < 0.2
    assert finished.wait(timeout=2)
    worker.join(timeout=1)


def test_inspecting_a_failed_generation_does_not_steal_the_retry() -> None:
    bus = InMemoryProgressBus()
    first = bus.watch(INTENT)
    _complete(bus, INTENT, "unavailable")
    second = bus.watch(INTENT)
    bus.emit(intent_id=INTENT, kind=ProgressEventKind.SOLICITATION_PREPARING, occurred_at=OCCURRED)
    assert bus.watch(INTENT, first) == first
    bus.emit(
        intent_id=INTENT,
        kind=ProgressEventKind.SOLICITATION_DISPATCHED,
        occurred_at=OCCURRED,
    )
    retry_events = bus.events_after(INTENT, None, second)
    assert [item.kind for item in retry_events] == [
        ProgressEventKind.SOLICITATION_PREPARING,
        ProgressEventKind.SOLICITATION_DISPATCHED,
    ]
