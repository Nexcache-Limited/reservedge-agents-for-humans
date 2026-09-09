from __future__ import annotations

from pathlib import Path

from comp_aws_01_helpers import DEMO_A

from itaa_aws_adapter.agent import compose_orchestrator
from itaa_aws_adapter.events import ACTIVITY_COPY

_FORBIDDEN = (
    "gemini",
    "google.adk",
    "itaa_google_adapter",
    "GOOGLE_GENAI",
    "vertexai",
    "generativelanguage",
)

_SRC = Path(__file__).resolve().parents[1] / "src" / "itaa_aws_adapter"


def test_adapter_sources_do_not_invoke_google() -> None:
    blob = ""
    for path in sorted(_SRC.glob("*.py")):
        blob += path.read_text(encoding="utf-8").lower()
    for needle in _FORBIDDEN:
        assert needle.lower() not in blob
    assert "bedrockagentcore" not in blob
    assert "from google" not in blob


def test_plan_events_are_buyer_safe() -> None:
    _model, _projection, events = compose_orchestrator().plan_turn(DEMO_A)
    kinds = [item["kind"] for item in events]
    assert kinds[0] == "OBJECTIVE_RECEIVED"
    assert "CHECKING_MISSING" in kinds
    assert "PLAN_READY" in kinds
    joined = " ".join(item["message"] for item in events).lower()
    assert "chain" not in joined
    assert "prompt" not in joined
    assert "skyshield" not in joined
    assert set(ACTIVITY_COPY) >= {
        "OBJECTIVE_RECEIVED",
        "CLARIFICATION_READY",
        "PLAN_READY",
        "FALLBACK_DETERMINISTIC",
        "FAILED_CLOSED",
    }


def test_plan_output_omits_account_and_model_ids() -> None:
    model, projection, events = compose_orchestrator().plan_turn(DEMO_A)
    dumped = model.model_dump_json() + projection.model_dump_json() + str(events)
    assert "123456789012" not in dumped
    assert "global.anthropic" not in dumped
    assert "bedrock" not in dumped.lower()
