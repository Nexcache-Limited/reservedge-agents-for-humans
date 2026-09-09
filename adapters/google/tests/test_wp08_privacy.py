from __future__ import annotations

from wp08_helpers import CORRELATION, JFK_TEXT

from itaa_google_adapter.agent import compose_agent
from itaa_google_adapter.ports import ExtractionRequest
from itaa_google_adapter.privacy import record_is_prompt_free, redact_secrets
from itaa_google_adapter.telemetry import RecordingTelemetry


def test_privacy_safe_logs_omit_prompts_and_secrets() -> None:
    sink = RecordingTelemetry()
    text = (
        f"{JFK_TEXT} Contact buyer@example.com with card 4111111111111111 "
        "and itinerary PNR ABC123 flight AA100 passenger synthetic-user."
    )
    result = compose_agent(telemetry=sink).extract(
        ExtractionRequest(text=text, category="airport_parking", correlation_id=CORRELATION)
    )
    assert result.proposal is None
    assert result.accepted is False
    assert sink.records
    for record in sink.records:
        payload = record.to_safe_mapping()
        assert record_is_prompt_free(payload)
        blob = str(payload)
        assert "buyer@example.com" not in blob
        assert "4111111111111111" not in blob
        assert JFK_TEXT not in blob
        assert "prompt_text" not in payload


def test_redaction_strips_synthetic_secrets() -> None:
    text = "synthetic buyer@example.com card 4111111111111111"
    redacted = redact_secrets(text)
    assert "buyer@example.com" not in redacted
    assert "4111" not in redacted
