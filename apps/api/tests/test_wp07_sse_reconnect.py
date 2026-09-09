from __future__ import annotations

from fastapi.testclient import TestClient
from wp04_helpers import A1_ID, A2_ID, BUYER, CORRELATION, CREATED_AT, EXPIRES_AT, OWNER
from wp06_fakes import jfk_payload

from itaa_api.app import create_app
from itaa_api.composition import build_facade
from itaa_application.local_progress import InMemoryProgressBus
from itaa_domain.value_objects import format_utc

PREFIX = "/v1/simulations/airport-parking"


def _gov(approval_id: object) -> dict[str, object]:
    return {
        "actorId": BUYER.actor_id.to_primitive(),
        "ownerId": OWNER.to_primitive(),
        "approvalId": approval_id.to_primitive(),
        "correlationId": CORRELATION.to_primitive(),
        "issuedAt": format_utc(CREATED_AT),
        "expiresAt": format_utc(EXPIRES_AT),
    }


def test_last_event_id_replays_from_the_next_sequence() -> None:
    bus = InMemoryProgressBus(heartbeat_seconds=0.05)
    client = TestClient(create_app(build_facade(progress=bus), progress=bus))
    created = client.post(f"{PREFIX}/intents", json=jfk_payload())
    intent_id = created.json()["intentId"]
    client.post(f"{PREFIX}/intents/{intent_id}/confirm", json=_gov(A1_ID))
    client.post(f"{PREFIX}/intents/{intent_id}/dispatch", json=_gov(A2_ID))
    generation_id = bus.generation_ids(str(intent_id))[-1]
    with client.stream(
        "GET",
        f"{PREFIX}/intents/{intent_id}/events?generationId={generation_id}",
        headers={"Last-Event-ID": "1"},
    ) as response:
        text = "".join(response.iter_text())
    assert "id: 1\n" not in text
    assert "event: SOLICITATION_DISPATCHED" in text
    assert "event: STREAM_COMPLETED" in text


def test_stream_before_dispatch_receives_live_then_closes() -> None:
    bus = InMemoryProgressBus(heartbeat_seconds=0.05)
    client = TestClient(create_app(build_facade(progress=bus), progress=bus))
    created = client.post(f"{PREFIX}/intents", json=jfk_payload())
    intent_id = created.json()["intentId"]
    client.post(f"{PREFIX}/intents/{intent_id}/confirm", json=_gov(A1_ID))
    bus.watch(str(intent_id))
    dispatched = client.post(f"{PREFIX}/intents/{intent_id}/dispatch", json=_gov(A2_ID))
    assert dispatched.status_code == 200
    kinds = [item.kind.value for item in bus.events_after(str(intent_id), None)]
    assert kinds[0] == "SOLICITATION_PREPARING"
    assert "SUPPLIER_WAITING" in kinds
    assert kinds[-1] == "STREAM_COMPLETED"
    generation_id = bus.generation_ids(str(intent_id))[-1]
    with client.stream(
        "GET",
        f"{PREFIX}/intents/{intent_id}/events?generationId={generation_id}",
    ) as response:
        text = "".join(response.iter_text())
    assert "event: STREAM_COMPLETED" in text
