from __future__ import annotations

from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from wp06_fakes import build_facade, jfk_payload

from itaa_api.app import create_app
from itaa_api.errors import (
    correlation_from,
    http_exception_handler,
    unhandled_error_handler,
)

PREFIX = "/v1/simulations/airport-parking"


def test_forbidden_extra_field_does_not_echo() -> None:
    client = TestClient(create_app(build_facade()))
    payload = jfk_payload()
    payload["email"] = "buyer@example.com"
    payload["secretToken"] = "super-secret"
    response = client.post(f"{PREFIX}/intents", json=payload)
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "schema_invalid"
    assert "buyer@example.com" not in response.text
    assert "super-secret" not in response.text
    assert "email" not in response.text


def test_unknown_intent_is_404() -> None:
    client = TestClient(create_app(build_facade()))
    response = client.get(f"{PREFIX}/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2zz")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_resource"


def test_live_mode_is_422_and_closed() -> None:
    client = TestClient(create_app(build_facade()))
    response = client.post(
        f"{PREFIX}/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3/transaction-authorizations",
        headers={"Idempotency-Key": "ik_01k2m3n4p5q6r7s8t9v0w1x2c1"},
        json={
            "actorId": "ar_01k2m3n4p5q6r7s8t9v0w1x2k1",
            "ownerId": "ar_01k2m3n4p5q6r7s8t9v0w1x2k1",
            "approvalId": "ap_01k2m3n4p5q6r7s8t9v0w1x2f3",
            "correlationId": "cr_01k2m3n4p5q6r7s8t9v0w1x2k2",
            "issuedAt": "2026-08-20T15:00:00Z",
            "expiresAt": "2026-08-22T15:00:00Z",
            "acceptanceId": "ac_01k2m3n4p5q6r7s8t9v0w1x2d1",
            "amountMinor": 1,
            "currency": "USD",
            "supplierToken": "sp_01k2m3n4p5q6r7s8t9v0w1x2b2",
            "action": "reserve_parking",
            "mode": "LIVE",
            "idempotencyKey": "ik_01k2m3n4p5q6r7s8t9v0w1x2c1",
        },
    )
    assert response.status_code in {404, 409, 422}
    assert "LIVE" not in response.text
    assert set(response.json()["error"]) == {"code", "field", "correlationId"}


def _request(headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": headers or [],
            "client": ("test", 0),
            "server": ("test", 80),
            "scheme": "http",
        }
    )


def test_invalid_correlation_and_closed_http_statuses() -> None:
    request = _request([(b"x-correlation-id", b"not-opaque")])
    assert correlation_from(request).startswith("cr_")
    client = TestClient(create_app(build_facade()))
    response = client.get(
        f"{PREFIX}/intents/not-an-intent",
        headers={"x-correlation-id": "not-opaque"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_opaque_syntax"


async def _exercise_handlers() -> None:
    request = _request()
    remapped = await http_exception_handler(request, StarletteHTTPException(status_code=418))
    assert remapped.status_code == 400
    closed = await unhandled_error_handler(request, RuntimeError("secret token"))
    assert closed.status_code == 500
    assert "secret" not in closed.body.decode()


def test_closed_handlers_do_not_echo_exception_text() -> None:
    import asyncio

    asyncio.run(_exercise_handlers())
