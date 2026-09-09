from __future__ import annotations

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
from wp06_fakes import build_facade, jfk_payload  # type: ignore[import-not-found]

from itaa_api.app import create_app
from itaa_domain.value_objects import format_utc

PREFIX = "/v1/simulations/airport-parking"


def test_e2e_jfk_create_confirm_dispatch_scores() -> None:
    client = TestClient(create_app(build_facade()))
    created = client.post(f"{PREFIX}/intents", json=jfk_payload())
    intent_id = created.json()["intentId"]
    client.post(
        f"{PREFIX}/intents/{intent_id}/confirm",
        json={
            "actorId": BUYER.actor_id.to_primitive(),
            "ownerId": OWNER.to_primitive(),
            "approvalId": A1_ID.to_primitive(),
            "correlationId": CORRELATION.to_primitive(),
            "issuedAt": format_utc(CREATED_AT),
            "expiresAt": format_utc(EXPIRES_AT),
        },
    )
    dispatched = client.post(
        f"{PREFIX}/intents/{intent_id}/dispatch",
        json={
            "actorId": BUYER.actor_id.to_primitive(),
            "ownerId": OWNER.to_primitive(),
            "approvalId": A2_ID.to_primitive(),
            "correlationId": CORRELATION.to_primitive(),
            "issuedAt": format_utc(CREATED_AT),
            "expiresAt": format_utc(EXPIRES_AT),
        },
    )
    assert dispatched.status_code == 200
    offers = dispatched.json()["offers"]
    by_id = {item["offerId"]: item for item in offers}
    assert by_id["of_01k2m3n4p5q6r7s8t9v0w1x2a2"]["rank"] == 1
    assert by_id["of_01k2m3n4p5q6r7s8t9v0w1x2a2"]["price"]["totalMinor"] == 14800
    assert by_id["of_01k2m3n4p5q6r7s8t9v0w1x2a1"]["rank"] == 2
    assert by_id["of_01k2m3n4p5q6r7s8t9v0w1x2a1"]["price"]["totalMinor"] == 11900
    assert by_id["of_01k2m3n4p5q6r7s8t9v0w1x2a3"]["rank"] == 3
    assert by_id["of_01k2m3n4p5q6r7s8t9v0w1x2a3"]["price"]["totalMinor"] == 16900
    for item in offers:
        assert "scoreMicros" not in item
        assert "termsHash" in item
    assert dispatched.json()["downside"]["delta"] == 2900
    assert len(dispatched.json()["supplierOutcomes"]) == 3
