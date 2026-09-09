from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from wp04_helpers import (  # type: ignore[import-not-found]
    A1_ID,
    A2_ID,
    BUYER,
    CORRELATION,
    CREATED_AT,
    EXPIRES_AT,
    OWNER,
)
from wp06_fakes import jfk_payload  # type: ignore[import-not-found]

from itaa_api.app import create_app
from itaa_api.composition import build_facade
from itaa_application.local_progress import InMemoryProgressBus
from itaa_domain.value_objects import format_utc

PREFIX = "/v1/simulations/airport-parking"
FORBIDDEN = (
    "buyerToken",
    "approvedPayloadHash",
    "prompt",
    "traceback",
    "password",
    "totalMinor",
    "scoreMicros",
    "idempotencyKey",
    "approvalId",
)


def _gov(approval_id: Any) -> dict[str, object]:
    return {
        "actorId": BUYER.actor_id.to_primitive(),
        "ownerId": OWNER.to_primitive(),
        "approvalId": approval_id.to_primitive(),
        "correlationId": CORRELATION.to_primitive(),
        "issuedAt": format_utc(CREATED_AT),
        "expiresAt": format_utc(EXPIRES_AT),
    }


def test_sse_payload_omits_identity_money_and_secrets() -> None:
    bus = InMemoryProgressBus(heartbeat_seconds=0.05)
    app = create_app(build_facade(progress=bus), progress=bus)
    client = TestClient(app)
    intent_id = client.post(f"{PREFIX}/intents", json=jfk_payload()).json()["intentId"]
    client.post(f"{PREFIX}/intents/{intent_id}/confirm", json=_gov(A1_ID))
    client.post(f"{PREFIX}/intents/{intent_id}/dispatch", json=_gov(A2_ID))
    generation_id = bus.generation_ids(str(intent_id))[-1]
    with client.stream(
        "GET",
        f"{PREFIX}/intents/{intent_id}/events?generationId={generation_id}",
    ) as response:
        text = "".join(response.iter_text())
    for needle in FORBIDDEN:
        assert needle not in text
    assert "event: STREAM_COMPLETED" in text
    description = app.openapi()["paths"][f"{PREFIX}/intents/{{intent_id}}/events"]["get"][
        "description"
    ]
    assert "process restart" in description.lower()
