"""Opt-in credentialed Vertex smoke. Ordinary CI skips this module."""

from __future__ import annotations

import json
import os
import time

import pytest
from wp08_helpers import (
    CORRELATION,
    JFK_TEXT,
    PARKDIRECT,
    PARKDIRECT_OFFER,
    SKYSHIELD,
    SKYSHIELD_OFFER,
    TERMINALFLEX,
    TERMINALFLEX_OFFER,
)

from itaa_google_adapter.agent import compose_agent
from itaa_google_adapter.fake import FakeModel
from itaa_google_adapter.live import live_sdk_available
from itaa_google_adapter.mode import MODE_LIVE, resolve_model_mode, vertex_config_ready
from itaa_google_adapter.ports import ExtractionRequest, ExtractionResponse
from itaa_google_adapter.privacy import REQUIREMENT_FIELDS
from itaa_google_adapter.resilience import APPROVED_LIVE_TIMEOUT_MS, SystemMonotonicClock
from itaa_google_adapter.telemetry import RecordingTelemetry

pytestmark = [
    pytest.mark.skipif(
        os.environ.get("ITAA_GOOGLE_LIVE_TEST") != "1",
        reason="credentialed Gemini tests require ITAA_GOOGLE_LIVE_TEST=1 and are skipped in CI",
    ),
    pytest.mark.filterwarnings("ignore::DeprecationWarning"),
]

REQUIRED_MODEL = "gemini-2.5-flash"
REQUIRED_EXACT_ENV: tuple[tuple[str, str], ...] = (
    ("ITAA_GOOGLE_MODEL_MODE", "live"),
    ("GOOGLE_GENAI_USE_VERTEXAI", "true"),
    ("ITAA_GEMINI_MODEL", REQUIRED_MODEL),
    ("ITAA_GOOGLE_TIMEOUT_MS", str(APPROVED_LIVE_TIMEOUT_MS)),
)
REQUIRED_NONEMPTY_ENV: tuple[str, ...] = (
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_LOCATION",
    "ITAA_GCP_REGION",
)
FORBIDDEN_FIXTURE_TOKENS: tuple[str, ...] = (
    "intentId",
    "buyerToken",
    "approvedPayloadHash",
    SKYSHIELD,
    PARKDIRECT,
    TERMINALFLEX,
    SKYSHIELD_OFFER,
    PARKDIRECT_OFFER,
    TERMINALFLEX_OFFER,
    "pi_01",
    "ap_01",
    "tx_01",
    "authorization",
)
LIVE_RUNS = 3


def _require_live_configuration() -> None:
    missing = [name for name, expected in REQUIRED_EXACT_ENV if os.environ.get(name) != expected]
    missing.extend(name for name in REQUIRED_NONEMPTY_ENV if not os.environ.get(name, "").strip())
    if missing:
        pytest.fail("live Vertex configuration missing: " + ",".join(missing))
    if not live_sdk_available():
        pytest.fail("google.adk is not installed")
    if not vertex_config_ready():
        pytest.fail("Vertex configuration is incomplete")
    if resolve_model_mode() != MODE_LIVE:
        pytest.fail("live test requires ITAA_GOOGLE_MODEL_MODE=live")


def _closed_evidence(result: ExtractionResponse) -> None:
    for span in result.evidence_spans:
        assert isinstance(span.field, str) and span.field
        assert span.field not in FORBIDDEN_FIXTURE_TOKENS
        assert "intentId" not in span.field
        assert isinstance(span.start, int)
        assert isinstance(span.end, int)
        assert span.end >= span.start >= 0
    for field, value in result.field_confidence.items():
        assert field in REQUIREMENT_FIELDS
        assert 0.0 <= float(value) <= 1.0
    for item in result.field_attributions:
        assert item.field in REQUIREMENT_FIELDS
        assert item.origin in {"extracted", "user_confirmed", "deterministic_default"}
        assert 0.0 <= float(item.confidence) <= 1.0


def _assert_jfk_proposal(result: ExtractionResponse) -> None:
    assert result.fallback is None
    assert result.rejection_code is None
    assert result.proposal is not None
    assert result.accepted is False
    assert result.requires_a1 is True
    assert result.missing_fields == ()
    assert result.ambiguous_fields == ()
    assert result.proposal["location"] == {"airportCode": "JFK"}
    assert result.proposal["serviceWindow"] == {
        "start": "2026-09-03T13:00:00Z",
        "end": "2026-09-08T22:00:00Z",
    }
    requirements = result.proposal["requirements"]
    assert isinstance(requirements, dict)
    assert requirements["vehicleClass"] == "standard"
    assert requirements["covered"] == "preferred"
    assert requirements["shuttleMaxMinutes"] == 20
    constraints = result.proposal["constraints"]
    assert isinstance(constraints, dict)
    assert constraints["currency"] == "USD"
    _closed_evidence(result)
    dumped = json.dumps(dict(result.proposal), separators=(",", ":"))
    for token in FORBIDDEN_FIXTURE_TOKENS:
        assert token not in dumped


def test_credentialed_vertex_extraction_is_strict() -> None:
    _require_live_configuration()
    sink = RecordingTelemetry()
    agent = compose_agent(telemetry=sink, clock=SystemMonotonicClock())
    assert type(agent._model).__name__ == "LiveModel"  # noqa: SLF001
    assert type(agent._model).__module__ == "itaa_google_adapter.live"  # noqa: SLF001
    assert not isinstance(agent._model, FakeModel)  # noqa: SLF001
    assert agent._policy.timeout_ms == APPROVED_LIVE_TIMEOUT_MS  # noqa: SLF001

    latencies: list[int] = []
    for index in range(1, LIVE_RUNS + 1):
        started = time.monotonic()
        result = agent.extract(
            ExtractionRequest(text=JFK_TEXT, category="airport_parking", correlation_id=CORRELATION)
        )
        latency_ms = int((time.monotonic() - started) * 1000)
        latencies.append(latency_ms)
        _assert_jfk_proposal(result)
        assert sink.records
        record = sink.records[-1]
        payload = record.to_safe_mapping()
        assert record.model_name == REQUIRED_MODEL
        assert record.task == "extract"
        assert "prompt_text" not in payload
        assert JFK_TEXT not in str(payload)
        print(
            f"LIVE_VERTEX_OK run={index}/{LIVE_RUNS} model={REQUIRED_MODEL} "
            f"task=extract proposal=present latency_ms={latency_ms}"
        )

    print(
        f"LIVE_VERTEX_OK aggregate={LIVE_RUNS}/{LIVE_RUNS} "
        f"latency_ms={','.join(str(item) for item in latencies)}"
    )
