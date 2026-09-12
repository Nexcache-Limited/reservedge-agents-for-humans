from __future__ import annotations

import urllib.request

import pytest
from fastapi.testclient import TestClient

from itaa_api.app import create_app

MILAN = "I'm travelling to Milan from Mumbai from 20 to 30 October."


def _forbid_live_extraction(*_args: object, **_kwargs: object) -> object:
    raise AssertionError("fake mode must not call a live extraction dependency")


def test_create_app_fake_mode_session_is_credential_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ITAA_AWS_MODEL_MODE", "fake")
    monkeypatch.setenv("ITAA_STAY_SEARCH_MODE", "sandbox")
    monkeypatch.delenv("ITAA_AWS_LIVE_INVOKE", raising=False)
    monkeypatch.delenv("ITAA_AWS_LIVE", raising=False)
    monkeypatch.delenv("ITAA_AWS_ADAPTER_URL", raising=False)
    monkeypatch.delenv("ITAA_AWS_LIVE_TEST", raising=False)
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.delenv("AWS_SESSION_TOKEN", raising=False)
    monkeypatch.delenv("ITAA_LITEAPI_API_KEY", raising=False)

    monkeypatch.setattr(urllib.request, "urlopen", _forbid_live_extraction)

    import itaa_aws_adapter.live as live_mod

    monkeypatch.setattr(live_mod, "LiveOrchestrator", _forbid_live_extraction)

    from itaa_liteapi_hotels.adapter import LiteApiStaySearchAdapter

    monkeypatch.setattr(LiteApiStaySearchAdapter, "search", _forbid_live_extraction)

    client = TestClient(create_app())
    response = client.post("/v1/agent/sessions", json={"objective": MILAN})
    assert response.status_code == 200, response.text
    body = response.json()
    facts = body["projection"]["facts"]
    assert body["projection"]["phase"] == "forming"
    assert facts["destination"] == "Milan"
    assert facts["originCity"] == "Mumbai"
    assert facts["startDate"] == "2026-10-20"
    assert facts["endDate"] == "2026-10-30"
    assert facts["parkingAirport"] == ""
    blob = response.text.lower()
    assert "jfk" not in blob
    assert "skyshield" not in blob
    assert body.get("staySearch") in (None, {})
    assert "Say the word" in body["buyerSafeMessage"]
    assert "will not search" not in body["buyerSafeMessage"].lower()
    questions = {item["id"] for item in body["projection"]["questions"]}
    assert "helpWith" not in questions
    by_kind = {item["kind"]: item for item in body["projection"]["tasks"]}
    assert by_kind.get("hotel", {}).get("provenance") != "explicit"
    assert "unavailable" not in blob
    provider = client.app.state.aws_provider
    assert provider is not None
    assert type(provider).__name__ != "HttpAwsProvider"


def test_hotel_chat_then_confirm_uses_labelled_fake_stay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ITAA_AWS_MODEL_MODE", "fake")
    monkeypatch.setenv("ITAA_STAY_SEARCH_MODE", "sandbox")
    monkeypatch.delenv("ITAA_AWS_ADAPTER_URL", raising=False)
    monkeypatch.delenv("ITAA_LITEAPI_API_KEY", raising=False)
    monkeypatch.setattr(urllib.request, "urlopen", _forbid_live_extraction)

    client = TestClient(create_app())
    created = client.post("/v1/agent/sessions", json={"objective": MILAN})
    assert created.status_code == 200, created.text
    session_id = created.json()["sessionId"]
    turned = client.post(
        f"/v1/agent/sessions/{session_id}/turns",
        json={"message": "I need a hotel and a rental car."},
    )
    assert turned.status_code == 200, turned.text
    pending = turned.json().get("pendingSearchAuthorization")
    assert isinstance(pending, dict)
    assert "stay.search" in pending["capabilities"]
    assert turned.json().get("staySearch") in (None, {})
    yes = client.post(
        f"/v1/agent/sessions/{session_id}/turns",
        json={"message": "yes"},
    )
    assert yes.status_code == 200, yes.text
    stay = yes.json()["staySearch"]
    assert isinstance(stay, dict)
    assert stay["status"] == "ok"
    assert stay["source"] == "fake"
    assert "not configured" not in str(stay.get("buyerSafeMessage") or "").lower()
    names = " ".join(str(item.get("name") or "") for item in stay["offers"]).lower()
    assert "milan" in names or "spadari" in names
    confirmed = client.post(f"/v1/agent/sessions/{session_id}/confirm", json={})
    assert confirmed.status_code == 200, confirmed.text
    body = confirmed.json()
    assert body["confirmed"] is True
    stay2 = body["staySearch"]
    assert stay2["status"] == "ok"
    assert stay2["source"] == "fake"
    assert stay2["offers"]
