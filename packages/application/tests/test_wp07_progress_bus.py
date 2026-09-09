from __future__ import annotations

from datetime import UTC, datetime

import pytest

from itaa_application.errors import ApplicationError
from itaa_application.local_progress import InMemoryProgressBus
from itaa_application.progress_events import ProgressEventKind

OCCURRED = datetime(2026, 8, 20, 16, 0, tzinfo=UTC)
INTENT = "pi_01k2m3n4p5q6r7s8t9v0w1x2y3"
OTHER = "pi_01k2m3n4p5q6r7s8t9v0w1x2y4"


def test_monotonic_sequences_and_replay() -> None:
    bus = InMemoryProgressBus()
    first = bus.emit(
        intent_id=INTENT, kind=ProgressEventKind.SOLICITATION_PREPARING, occurred_at=OCCURRED
    )
    second = bus.emit(
        intent_id=INTENT, kind=ProgressEventKind.SOLICITATION_DISPATCHED, occurred_at=OCCURRED
    )
    assert first.sequence == 1
    assert second.sequence == 2
    replayed = bus.events_after(INTENT, 1)
    assert [item.sequence for item in replayed] == [2]


def test_bounded_buffer_gap_fails_closed() -> None:
    bus = InMemoryProgressBus(max_events=2)
    bus.emit(intent_id=INTENT, kind=ProgressEventKind.SOLICITATION_PREPARING, occurred_at=OCCURRED)
    bus.emit(intent_id=INTENT, kind=ProgressEventKind.SOLICITATION_DISPATCHED, occurred_at=OCCURRED)
    bus.emit(intent_id=INTENT, kind=ProgressEventKind.VALIDATION_COMPLETED, occurred_at=OCCURRED)
    with pytest.raises(ApplicationError) as raised:
        bus.events_after(INTENT, 1)
    assert raised.value.field == "intentId"
    assert raised.value.code == "expired"
    remaining = bus.events_after(INTENT, 2)
    assert [item.kind for item in remaining] == [
        ProgressEventKind.VALIDATION_COMPLETED,
    ]


def test_cross_intent_isolation() -> None:
    bus = InMemoryProgressBus()
    bus.emit(intent_id=INTENT, kind=ProgressEventKind.SOLICITATION_PREPARING, occurred_at=OCCURRED)
    bus.emit(intent_id=OTHER, kind=ProgressEventKind.RANKING_COMPLETED, occurred_at=OCCURRED)
    assert bus.events_after(INTENT, None)[0].kind is ProgressEventKind.SOLICITATION_PREPARING
    assert bus.events_after(OTHER, None)[0].kind is ProgressEventKind.RANKING_COMPLETED


def test_completed_intents_are_evicted_before_unbounded_growth() -> None:
    bus = InMemoryProgressBus(max_intents=1)
    bus.emit(
        intent_id=INTENT,
        kind=ProgressEventKind.STREAM_COMPLETED,
        occurred_at=OCCURRED,
        status="complete",
        terminal=True,
    )
    bus.emit(intent_id=OTHER, kind=ProgressEventKind.SOLICITATION_PREPARING, occurred_at=OCCURRED)
    assert bus.events_after(INTENT, None) == ()
    assert len(bus.events_after(OTHER, None)) == 1


def test_subscribe_replays_then_heartbeats_without_blocking_emit() -> None:
    bus = InMemoryProgressBus(heartbeat_seconds=0.01)
    bus.watch(INTENT)
    bus.emit(intent_id=INTENT, kind=ProgressEventKind.SOLICITATION_PREPARING, occurred_at=OCCURRED)
    stream = bus.subscribe(INTENT, None)
    first = next(stream)
    assert first is not None
    assert first.kind is ProgressEventKind.SOLICITATION_PREPARING
    heartbeat = next(stream)
    assert heartbeat is None
    bus.emit(
        intent_id=INTENT,
        kind=ProgressEventKind.STREAM_COMPLETED,
        occurred_at=OCCURRED,
        status="complete",
        terminal=True,
    )
    terminal = next(stream)
    assert terminal is not None
    assert terminal.terminal is True
