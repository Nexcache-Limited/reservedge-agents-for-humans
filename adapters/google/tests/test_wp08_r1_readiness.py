from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from itaa_google_adapter.app import create_google_app


def test_fake_mode_readyz_is_200(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITAA_GOOGLE_MODEL_MODE", "fake")
    client = TestClient(create_google_app())
    ready = client.get("/readyz")
    assert ready.status_code == 200
    body = ready.json()
    assert body["status"] == "ready"
    assert body["environment"] == "local_simulation"
    assert body["durability"] == "unsupported"
    dumped = ready.text.lower()
    assert "aiza" not in dumped
    assert "project" not in dumped
    assert "credential" not in dumped


def test_live_mode_without_vertex_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITAA_GOOGLE_MODEL_MODE", "live")
    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    client = TestClient(create_google_app())
    ready = client.get("/readyz")
    assert ready.status_code == 503
    body = ready.json()
    assert body == {
        "status": "unavailable",
        "adapter": "live",
        "environment": "local_simulation",
    }
    dumped = ready.text.lower()
    assert "aiza" not in dumped
    assert "api_key" not in dumped
    assert "owner-project" not in dumped
    assert "begin private key" not in dumped


def test_unknown_mode_readyz_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITAA_GOOGLE_MODEL_MODE", "maybe")
    client = TestClient(create_google_app())
    ready = client.get("/readyz")
    assert ready.status_code == 503
    assert ready.json()["status"] == "unavailable"
    assert ready.json()["adapter"] == "unknown"
    assert ready.json()["environment"] == "local_simulation"
