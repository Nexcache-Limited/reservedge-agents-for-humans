"""Process-local in-memory progress bus. Restart discards all events."""

from __future__ import annotations

import secrets
from collections import OrderedDict, deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from threading import Condition

from itaa_application.errors import ApplicationError
from itaa_application.progress_events import (
    ProgressEvent,
    ProgressEventKind,
    validate_generation_id,
    validate_progress_fields,
)

MAX_EVENTS_PER_GENERATION = 64
MAX_INTENTS = 128
MAX_GENERATIONS_PER_INTENT = 2


def mint_progress_generation_id() -> str:
    return "pg_" + secrets.token_hex(13)


@dataclass
class _GenerationBuffer:
    generation_id: str
    events: deque[ProgressEvent] = field(default_factory=deque)
    dropped_below: int = 0
    completed: bool = False


@dataclass
class _IntentStreams:
    generations: OrderedDict[str, _GenerationBuffer] = field(default_factory=OrderedDict)
    active_id: str | None = None


class InMemoryProgressBus:
    """Bounded per-intent, per-generation buffer. Publishers never wait on subscribers.

    Process-local: a restart loses events. Each authorized dispatch attempt uses a
    distinct opaque generation id. Reconnect/Last-Event-ID is scoped to one generation.
    """

    def __init__(
        self,
        *,
        max_events: int = MAX_EVENTS_PER_GENERATION,
        max_intents: int = MAX_INTENTS,
        max_generations: int = MAX_GENERATIONS_PER_INTENT,
        heartbeat_seconds: float = 1.0,
        generation_ids: Callable[[], str] | None = None,
    ) -> None:
        self._max_events = max_events
        self._max_intents = max_intents
        self._max_generations = max_generations
        self._heartbeat_seconds = heartbeat_seconds
        self._mint = generation_ids or mint_progress_generation_id
        self._streams: OrderedDict[str, _IntentStreams] = OrderedDict()
        self._condition = Condition()

    def watch(self, intent_id: str, generation_id: str | None = None) -> str:
        with self._condition:
            if generation_id is not None:
                validate_generation_id(generation_id)
                streams = self._streams.get(intent_id)
                if streams is None or generation_id not in streams.generations:
                    raise ApplicationError("generationId", "unknown_resource")
                self._streams.move_to_end(intent_id)
                return generation_id
            streams = self._streams.get(intent_id)
            if streams is not None and streams.active_id is not None:
                current = streams.generations[streams.active_id]
                if not current.completed:
                    self._streams.move_to_end(intent_id)
                    return current.generation_id
            return self._open_generation(intent_id)

    def has_started(self, intent_id: str) -> bool:
        with self._condition:
            streams = self._streams.get(intent_id)
            if streams is None or streams.active_id is None:
                return False
            buffer = streams.generations[streams.active_id]
            if buffer.completed:
                return False
            return any(not event.terminal for event in buffer.events)

    def abandon_empty(self, intent_id: str) -> None:
        with self._condition:
            streams = self._streams.get(intent_id)
            if streams is None or streams.active_id is None:
                return
            buffer = streams.generations[streams.active_id]
            if buffer.completed or buffer.events:
                return
            buffer.completed = True
            self._condition.notify_all()

    def emit(
        self,
        *,
        intent_id: str,
        kind: ProgressEventKind,
        occurred_at: datetime,
        supplier_token: str | None = None,
        status: str | None = None,
        correlation_id: str | None = None,
        terminal: bool = False,
    ) -> ProgressEvent:
        with self._condition:
            streams = self._streams.get(intent_id)
            if streams is None or streams.active_id is None:
                generation_id = self._open_generation(intent_id)
                streams = self._streams[intent_id]
            else:
                generation_id = streams.active_id
                current = streams.generations[generation_id]
                if current.completed:
                    generation_id = self._open_generation(intent_id)
                    streams = self._streams[intent_id]
            buffer = streams.generations[generation_id]
            sequence = buffer.events[-1].sequence + 1 if buffer.events else buffer.dropped_below + 1
            validate_progress_fields(
                intent_id=intent_id,
                generation_id=generation_id,
                kind=kind,
                sequence=sequence,
                occurred_at=occurred_at,
                supplier_token=supplier_token,
                status=status,
                correlation_id=correlation_id,
                terminal=terminal,
            )
            event = ProgressEvent(
                intent_id=intent_id,
                generation_id=generation_id,
                kind=kind,
                sequence=sequence,
                occurred_at=occurred_at,
                simulation=True,
                supplier_token=supplier_token,
                status=status,
                correlation_id=correlation_id,
                terminal=terminal,
            )
            if len(buffer.events) >= self._max_events:
                dropped = buffer.events.popleft()
                buffer.dropped_below = dropped.sequence
            buffer.events.append(event)
            if terminal:
                buffer.completed = True
            self._condition.notify_all()
            return event

    def events_after(
        self,
        intent_id: str,
        last_sequence: int | None,
        generation_id: str | None = None,
    ) -> tuple[ProgressEvent, ...]:
        with self._condition:
            buffer = self._resolve_buffer(intent_id, generation_id, missing_ok=True)
            if buffer is None:
                return ()
            return self._replay(buffer, last_sequence)

    def subscribe(
        self,
        intent_id: str,
        last_sequence: int | None,
        generation_id: str | None = None,
    ) -> Iterator[ProgressEvent | None]:
        last = last_sequence
        pinned = generation_id
        while True:
            heartbeat = False
            batch: tuple[ProgressEvent, ...] = ()
            with self._condition:
                buffer = self._resolve_buffer(intent_id, pinned, missing_ok=True)
                if buffer is None:
                    notified = self._condition.wait(timeout=self._heartbeat_seconds)
                    if not notified:
                        heartbeat = True
                else:
                    pinned = buffer.generation_id
                    batch = self._replay(buffer, last)
                    if not batch:
                        if buffer.completed:
                            return
                        notified = self._condition.wait(timeout=self._heartbeat_seconds)
                        if not notified:
                            heartbeat = True
            if heartbeat:
                yield None
                continue
            for event in batch:
                last = event.sequence
                yield event
                if event.terminal:
                    return

    def generation_ids(self, intent_id: str) -> tuple[str, ...]:
        with self._condition:
            streams = self._streams.get(intent_id)
            if streams is None:
                return ()
            return tuple(streams.generations)

    def _open_generation(self, intent_id: str) -> str:
        streams = self._streams.get(intent_id)
        if streams is None:
            if len(self._streams) >= self._max_intents:
                evicted = next(
                    (key for key, item in self._streams.items() if _intent_completed(item)),
                    None,
                )
                if evicted is None:
                    raise ApplicationError("intentId", "expired")
                del self._streams[evicted]
            streams = _IntentStreams()
            self._streams[intent_id] = streams
        else:
            self._streams.move_to_end(intent_id)
        self._evict_old_generations(streams)
        generation_id = validate_generation_id(self._mint())
        streams.generations[generation_id] = _GenerationBuffer(generation_id=generation_id)
        streams.active_id = generation_id
        self._condition.notify_all()
        return generation_id

    def _evict_old_generations(self, streams: _IntentStreams) -> None:
        while len(streams.generations) >= self._max_generations:
            oldest = next(
                (key for key, item in streams.generations.items() if item.completed),
                None,
            )
            if oldest is None:
                raise ApplicationError("generationId", "expired")
            del streams.generations[oldest]
            if streams.active_id == oldest:
                streams.active_id = next(reversed(streams.generations), None)

    def _resolve_buffer(
        self,
        intent_id: str,
        generation_id: str | None,
        *,
        missing_ok: bool,
    ) -> _GenerationBuffer | None:
        streams = self._streams.get(intent_id)
        if generation_id is not None:
            validate_generation_id(generation_id)
            if streams is None or generation_id not in streams.generations:
                raise ApplicationError("generationId", "unknown_resource")
            return streams.generations[generation_id]
        if streams is None:
            if not missing_ok:
                raise ApplicationError("intentId", "unknown_resource")
            return None
        if streams.active_id is None:
            return None
        return streams.generations[streams.active_id]

    def _replay(
        self, buffer: _GenerationBuffer, last_sequence: int | None
    ) -> tuple[ProgressEvent, ...]:
        if last_sequence is None:
            return tuple(buffer.events)
        if last_sequence <= buffer.dropped_below:
            raise ApplicationError("intentId", "expired")
        sequences = {item.sequence for item in buffer.events}
        if last_sequence not in sequences:
            raise ApplicationError("lastEventId", "schema_invalid")
        return tuple(item for item in buffer.events if item.sequence > last_sequence)


def _intent_completed(streams: _IntentStreams) -> bool:
    if not streams.generations:
        return False
    return all(item.completed for item in streams.generations.values())
