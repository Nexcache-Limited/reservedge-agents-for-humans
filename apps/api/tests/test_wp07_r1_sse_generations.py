from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from wp04_helpers import A1_ID, A2_ID, BUYER, CORRELATION, CREATED_AT, EXPIRES_AT, OWNER
from wp06_fakes import jfk_payload

from itaa_api.app import create_app
from itaa_api.composition import build_facade
from itaa_application.golden_path import FaultInjector
from itaa_application.local_progress import InMemoryProgressBus
from itaa_application.progress_events import ProgressEventKind
from itaa_domain.value_objects import format_utc

PREFIX = "/v1/simulations/airport-parking"
UNKNOWN_GENERATION = "pg_" + ("0" * 26)


def _gov(approval_id: object) -> dict[str, object]:
    return {
        "actorId": BUYER.actor_id.to_primitive(),
        "ownerId": OWNER.to_primitive(),
        "approvalId": approval_id.to_primitive(),
        "correlationId": CORRELATION.to_primitive(),
        "issuedAt": format_utc(CREATED_AT),
        "expiresAt": format_utc(EXPIRES_AT),
    }


def _confirmed(client: TestClient) -> str:
    created = client.post(f"{PREFIX}/intents", json=jfk_payload())
    assert created.status_code == 200
    intent_id = created.json()["intentId"]
    confirmed = client.post(f"{PREFIX}/intents/{intent_id}/confirm", json=_gov(A1_ID))
    assert confirmed.status_code == 200
    return str(intent_id)


def test_sse_retry_does_not_replay_previous_unavailable() -> None:
    faults = FaultInjector()
    bus = InMemoryProgressBus(heartbeat_seconds=0.05)
    client = TestClient(create_app(build_facade(progress=bus, faults=faults), progress=bus))
    intent_id = _confirmed(client)
    faults.fail_at("a2.after_approval_and_audit")
    failed = client.post(f"{PREFIX}/intents/{intent_id}/dispatch", json=_gov(A2_ID))
    assert failed.status_code == 500
    first = bus.generation_ids(intent_id)[0]
    failed_events = bus.events_after(intent_id, None, first)
    assert failed_events[-1].status == "unavailable"
    retried = client.post(f"{PREFIX}/intents/{intent_id}/dispatch", json=_gov(A2_ID))
    assert retried.status_code == 200
    body = retried.json()
    by_token = {item["supplierToken"]: item for item in body["offers"]}
    assert by_token["sp_01k2m3n4p5q6r7s8t9v0w1x2b2"]["rank"] == 1
    assert by_token["sp_01k2m3n4p5q6r7s8t9v0w1x2b2"]["price"]["totalMinor"] == 14800
    assert "scoreMicros" not in by_token["sp_01k2m3n4p5q6r7s8t9v0w1x2b2"]
    assert body["downside"]["delta"] == 2900
    second = bus.generation_ids(intent_id)[1]
    with client.stream(
        "GET",
        f"{PREFIX}/intents/{intent_id}/events?generationId={second}",
    ) as response:
        text = "".join(response.iter_text())
    assert "event: SOLICITATION_PREPARING" in text
    assert "event: SUPPLIER_WAITING" in text
    assert '"status":"complete"' in text
    assert '"status":"unavailable"' not in text
    with client.stream(
        "GET",
        f"{PREFIX}/intents/{intent_id}/events?generationId={first}",
    ) as previous:
        prior = "".join(previous.iter_text())
    assert '"status":"unavailable"' in prior
    assert second not in prior


def test_sse_reconnect_within_generation_skips_seen_sequence() -> None:
    bus = InMemoryProgressBus(heartbeat_seconds=0.05)
    client = TestClient(create_app(build_facade(progress=bus), progress=bus))
    intent_id = _confirmed(client)
    dispatched = client.post(f"{PREFIX}/intents/{intent_id}/dispatch", json=_gov(A2_ID))
    assert dispatched.status_code == 200
    generation_id = bus.generation_ids(intent_id)[-1]
    with client.stream(
        "GET",
        f"{PREFIX}/intents/{intent_id}/events?generationId={generation_id}&lastEventId=1",
    ) as response:
        text = "".join(response.iter_text())
    assert "id: 1\n" not in text
    assert "event: SOLICITATION_DISPATCHED" in text
    assert f'"generationId":"{generation_id}"' in text


def test_sse_rejects_another_generation_last_event_id() -> None:
    bus = InMemoryProgressBus(heartbeat_seconds=0.05)
    client = TestClient(create_app(build_facade(progress=bus), progress=bus))
    intent_id = _confirmed(client)
    client.post(f"{PREFIX}/intents/{intent_id}/dispatch", json=_gov(A2_ID))
    first = bus.generation_ids(intent_id)[0]
    last = bus.events_after(intent_id, None, first)[-1].sequence
    second = bus.watch(intent_id)
    bus.emit(
        intent_id=intent_id,
        kind=ProgressEventKind.SOLICITATION_PREPARING,
        occurred_at=datetime(2026, 8, 20, 16, 0, tzinfo=UTC),
    )
    response = client.get(
        f"{PREFIX}/intents/{intent_id}/events?generationId={second}&lastEventId={last}",
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "schema_invalid"
    assert response.json()["error"]["field"] == "lastEventId"


def test_unknown_generation_and_cross_intent_fail_closed() -> None:
    bus = InMemoryProgressBus(heartbeat_seconds=0.05)
    client = TestClient(create_app(build_facade(progress=bus), progress=bus))
    first = _confirmed(client)
    payload = jfk_payload()
    payload["intentId"] = "pi_01k2m3n4p5q6r7s8t9v0w1x2y9"
    second = client.post(f"{PREFIX}/intents", json=payload).json()["intentId"]
    client.post(f"{PREFIX}/intents/{first}/dispatch", json=_gov(A2_ID))
    stolen = bus.generation_ids(str(first))[0]
    unknown = client.get(f"{PREFIX}/intents/{first}/events?generationId={UNKNOWN_GENERATION}")
    assert unknown.status_code == 404
    assert unknown.json()["error"]["field"] == "generationId"
    crossed = client.get(f"{PREFIX}/intents/{second}/events?generationId={stolen}")
    assert crossed.status_code == 404
    assert crossed.json()["error"]["code"] == "unknown_resource"
    malformed = client.get(
        f"{PREFIX}/intents/{first}/events?generationId=ap_01k2m3n4p5q6r7s8t9v0w1x2f1"
    )
    assert malformed.status_code == 400
    assert malformed.json()["error"]["field"] == "generationId"
