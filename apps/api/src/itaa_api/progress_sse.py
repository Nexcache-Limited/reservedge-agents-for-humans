"""SSE adapter for local progress events. Process-local; restart loses the buffer."""

from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import StreamingResponse

from itaa_application.errors import ApplicationError
from itaa_application.golden_path import GoldenPathFacade
from itaa_application.local_progress import InMemoryProgressBus
from itaa_application.progress_events import ProgressEvent, validate_generation_id
from itaa_domain.errors import DomainInvariantError
from itaa_domain.identifiers import IntentId

PREFIX = "/v1/simulations/airport-parking"
OPENAPI_TAG = "local-simulation"

router = APIRouter()


def _facade(request: Request) -> GoldenPathFacade:
    facade = request.app.state.facade
    if not isinstance(facade, GoldenPathFacade):
        raise ApplicationError("internal", "closed")
    return facade


def _bus(request: Request) -> InMemoryProgressBus:
    bus = request.app.state.progress
    if not isinstance(bus, InMemoryProgressBus):
        raise ApplicationError("internal", "closed")
    return bus


def _intent_id(raw: str) -> IntentId:
    try:
        return IntentId(raw)
    except DomainInvariantError as exc:
        raise ApplicationError(exc.field, exc.code) from None


def _last_sequence(raw: str | None) -> int | None:
    if raw is None or raw == "":
        return None
    if not raw.isdigit():
        raise ApplicationError("Last-Event-ID", "schema_invalid")
    value = int(raw)
    if value < 1:
        raise ApplicationError("Last-Event-ID", "schema_invalid")
    return value


def format_sse(event: ProgressEvent) -> str:
    payload = json.dumps(event.to_public(), separators=(",", ":"), sort_keys=True)
    return f"id: {event.sequence}\nevent: {event.kind.value}\ndata: {payload}\n\n"


def _stream(
    bus: InMemoryProgressBus,
    intent_key: str,
    last: int | None,
    generation_id: str,
) -> Iterator[str]:
    for item in bus.subscribe(intent_key, last, generation_id):
        if item is None:
            yield ": keepalive\n\n"
            continue
        yield format_sse(item)
        if item.terminal:
            return


@router.get(
    f"{PREFIX}/intents/{{intent_id}}/events",
    responses={
        404: {"description": "Unknown intent or generation"},
        422: {"description": "Expired or gapped buffer"},
    },
    tags=[OPENAPI_TAG],
    summary="Buyer-safe solicitation progress stream",
    description=(
        "Server-sent events for one local simulated intent and one progress generation. "
        "text/event-stream with monotonic id sequence numbers within a generation. "
        "Reconnect with Last-Event-ID and generationId for the same attempt only. "
        "A later dispatch retry opens a new generation and does not replay a previous "
        "STREAM_COMPLETED/unavailable event. Bounded in-memory buffer; process restart "
        "discards events. Progress is operational only; the dispatch POST snapshot remains "
        "authoritative. STREAM_COMPLETED closes the stream. No durable brokers or WebSockets."
    ),
)
def intent_events(
    request: Request,
    intent_id: str,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    last_event_query: str | None = Query(default=None, alias="lastEventId"),
    generation_id: str | None = Query(default=None, alias="generationId"),
) -> StreamingResponse:
    parsed = _intent_id(intent_id)
    _facade(request).get_buyer_snapshot(parsed)
    last = _last_sequence(last_event_id or last_event_query)
    if generation_id is not None:
        validate_generation_id(generation_id)
    bus = _bus(request)
    assigned = bus.watch(parsed.to_primitive(), generation_id)
    bus.events_after(parsed.to_primitive(), last, assigned)
    return StreamingResponse(
        _stream(bus, parsed.to_primitive(), last, assigned),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
