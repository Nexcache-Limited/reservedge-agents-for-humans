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


def test_events_do_not_leak_across_intents_or_supplier_lanes() -> None:
    bus = InMemoryProgressBus(heartbeat_seconds=0.05)
    client = TestClient(create_app(build_facade(progress=bus), progress=bus))
    first = client.post(f"{PREFIX}/intents", json=jfk_payload()).json()["intentId"]
    payload = jfk_payload()
    payload["intentId"] = "pi_01k2m3n4p5q6r7s8t9v0w1x2y9"
    second = client.post(f"{PREFIX}/intents", json=payload).json()["intentId"]
    client.post(f"{PREFIX}/intents/{first}/confirm", json=_gov(A1_ID))
    client.post(f"{PREFIX}/intents/{first}/dispatch", json=_gov(A2_ID))
    first_events = bus.events_after(str(first), None)
    second_events = bus.events_after(str(second), None)
    assert second_events == ()
    assert all(item.intent_id == first for item in first_events)
    tokens = {item.supplier_token for item in first_events if item.supplier_token is not None}
    assert tokens == {
        "sp_01k2m3n4p5q6r7s8t9v0w1x2b1",
        "sp_01k2m3n4p5q6r7s8t9v0w1x2b2",
        "sp_01k2m3n4p5q6r7s8t9v0w1x2b3",
    }
    with client.stream(
        "GET",
        f"{PREFIX}/intents/{first}/events?generationId={bus.generation_ids(str(first))[-1]}",
    ) as response:
        text = "".join(response.iter_text())
    assert second not in text
    assert "event: STREAM_COMPLETED" in text
