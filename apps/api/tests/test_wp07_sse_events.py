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


def _confirmed_intent(client: TestClient) -> str:
    created = client.post(f"{PREFIX}/intents", json=jfk_payload())
    assert created.status_code == 200
    intent_id = created.json()["intentId"]
    confirmed = client.post(f"{PREFIX}/intents/{intent_id}/confirm", json=_gov(A1_ID))
    assert confirmed.status_code == 200
    return str(intent_id)


def test_sse_replays_ordered_privacy_safe_progress_after_dispatch() -> None:
    bus = InMemoryProgressBus(heartbeat_seconds=0.05)
    client = TestClient(create_app(build_facade(progress=bus), progress=bus))
    intent_id = _confirmed_intent(client)
    dispatched = client.post(f"{PREFIX}/intents/{intent_id}/dispatch", json=_gov(A2_ID))
    assert dispatched.status_code == 200
    body = dispatched.json()
    by_token = {item["supplierToken"]: item for item in body["offers"]}
    assert by_token["sp_01k2m3n4p5q6r7s8t9v0w1x2b2"]["rank"] == 1
    assert by_token["sp_01k2m3n4p5q6r7s8t9v0w1x2b2"]["price"]["totalMinor"] == 14800
    assert "scoreMicros" not in by_token["sp_01k2m3n4p5q6r7s8t9v0w1x2b2"]
    assert body["downside"]["delta"] == 2900
    generation_id = bus.generation_ids(str(intent_id))[-1]
    with client.stream(
        "GET",
        f"{PREFIX}/intents/{intent_id}/events?generationId={generation_id}",
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        text = "".join(response.iter_text())
    assert "event: SOLICITATION_PREPARING" in text
    assert "event: SUPPLIER_WAITING" in text
    assert "event: SUPPLIER_OFFER_RECEIVED" in text
    assert "event: STREAM_COMPLETED" in text
    assert "generationId" in text
    assert "totalMinor" not in text
    assert "scoreMicros" not in text
    assert "approvalId" not in text


def test_unknown_intent_events_fail_closed() -> None:
    client = TestClient(create_app())
    response = client.get(f"{PREFIX}/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2zz/events")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_resource"
    assert "pi_01" not in response.json()["error"]["code"]
