from __future__ import annotations

from fastapi.testclient import TestClient
from wp06_fakes import build_facade  # type: ignore[import-not-found]

from itaa_api.app import create_app

PREFIX = "/v1/simulations/airport-parking"


def test_default_fastapi_422_detail_cannot_escape() -> None:
    client = TestClient(create_app(build_facade()))
    response = client.post(
        f"{PREFIX}/intents",
        json={"email": "leak@example.com", "card": "4111111111111111"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "schema_invalid"
    assert "detail" not in response.json()
    assert "leak@example.com" not in response.text
    assert "4111111111111111" not in response.text
    assert "input" not in response.text.lower() or "intent" in response.text.lower()
