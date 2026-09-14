from __future__ import annotations

import os

import pytest

from itaa_application.errors import ApplicationError
from itaa_aws_adapter.agent import FakeOrchestrator, compose_orchestrator
from itaa_aws_adapter.live import LiveOrchestrator, _fallback_turn
from itaa_aws_adapter.schemas import PlanAnswers, PlanTurn


def test_first_cycle_structured_output_context_forces_tool() -> None:
    from itaa_aws_adapter.live import _first_cycle_structured_output_context

    context = _first_cycle_structured_output_context()(PlanTurn)
    assert context.forced_mode is True
    assert context.force_attempted is True
    assert context.tool_choice == {"any": {}}
    assert context.expected_tool_name == "PlanTurn"


def test_live_without_invoke_flag_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITAA_AWS_MODEL_MODE", "live")
    monkeypatch.setenv("ITAA_AWS_TIMEOUT_MS", "30000")
    monkeypatch.delenv("ITAA_AWS_LIVE_INVOKE", raising=False)
    inner = compose_orchestrator()._inner  # noqa: SLF001
    assert type(inner).__name__ == "LiveOrchestrator"
    assert not isinstance(inner, FakeOrchestrator)
    with pytest.raises(ApplicationError, match="model: unavailable"):
        inner.plan_turn("hello")
    with pytest.raises(ApplicationError, match="model: unavailable"):
        inner.execute_turn("get_supported_capabilities", {})


def test_live_authorized_uses_injected_invoker_not_fake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ITAA_AWS_MODEL_MODE", "live")
    monkeypatch.setenv("ITAA_AWS_TIMEOUT_MS", "30000")
    monkeypatch.setenv("ITAA_AWS_LIVE_INVOKE", "1")

    def invoker(objective: str, answers: PlanAnswers, model_id: str, timeout_ms: int) -> PlanTurn:
        del answers, timeout_ms
        assert model_id == "global.anthropic.claude-sonnet-4-6"
        return PlanTurn(
            understanding="Airport parking mentioned.",
            facts=_fallback_turn(objective, PlanAnswers()).facts,
            evidence=[],
            blockingQuestions=[],
            suggestedTasks=[],
            buyerSafeMessage="Parking is proposed only until evidence is checked.",
            fallback=False,
            requirementPatches=[],
        )

    agent = LiveOrchestrator(plan_invoker=invoker)
    model, projection, events = agent.plan_turn(
        "I need parking at MAN next week.",
    )
    assert agent.last_plan_turn is model
    assert model.fallback is False
    assert type(agent).__name__ == "LiveOrchestrator"
    assert all(event["kind"] != "FAILED_CLOSED" for event in events)
    dumped = model.model_dump_json() + projection.model_dump_json() + str(events)
    assert "global.anthropic" not in dumped
    assert "156332912967" not in dumped
    assert "bedrock" not in dumped.lower()


def test_live_timeout_uses_labelled_projector_not_fake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ITAA_AWS_MODEL_MODE", "live")
    monkeypatch.setenv("ITAA_AWS_TIMEOUT_MS", "30000")
    monkeypatch.setenv("ITAA_AWS_LIVE_INVOKE", "1")

    def invoker(objective: str, answers: PlanAnswers, model_id: str, timeout_ms: int) -> PlanTurn:
        del objective, answers, model_id, timeout_ms
        raise TimeoutError("deadline")

    model, _projection, events = LiveOrchestrator(plan_invoker=invoker).plan_turn(
        "Going away next month"
    )
    assert model.fallback is True
    assert any(event["kind"] == "FALLBACK_DETERMINISTIC" for event in events)
    assert model.buyerSafeMessage == "Using the local planner (labelled)."


def test_live_schema_invalid_uses_labelled_projector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ITAA_AWS_MODEL_MODE", "live")
    monkeypatch.setenv("ITAA_AWS_TIMEOUT_MS", "30000")
    monkeypatch.setenv("ITAA_AWS_LIVE_INVOKE", "1")

    def invoker(objective: str, answers: PlanAnswers, model_id: str, timeout_ms: int) -> PlanTurn:
        del answers, model_id, timeout_ms
        return PlanTurn.model_validate({"understanding": objective})

    model, _projection, events = LiveOrchestrator(plan_invoker=invoker).plan_turn("Trip")
    assert model.fallback is True
    assert any(event["kind"] == "FALLBACK_DETERMINISTIC" for event in events)


def test_live_auth_error_does_not_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITAA_AWS_MODEL_MODE", "live")
    monkeypatch.setenv("ITAA_AWS_TIMEOUT_MS", "30000")
    monkeypatch.setenv("ITAA_AWS_LIVE_INVOKE", "1")

    def invoker(objective: str, answers: PlanAnswers, model_id: str, timeout_ms: int) -> PlanTurn:
        del objective, answers, model_id, timeout_ms
        raise ApplicationError("model", "unavailable")

    with pytest.raises(ApplicationError, match="model: unavailable"):
        LiveOrchestrator(plan_invoker=invoker).plan_turn("Trip")


def test_live_ready_and_authorized_execute_still_closed_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ITAA_AWS_MODEL_MODE", "live")
    monkeypatch.setenv("ITAA_AWS_TIMEOUT_MS", "30000")
    monkeypatch.setenv("ITAA_AWS_LIVE_INVOKE", "1")
    from itaa_aws_adapter.live import live_runtime_ready

    assert live_runtime_ready() is True
    with pytest.raises(ApplicationError, match="objective: required"):
        LiveOrchestrator(plan_invoker=lambda *_: None).plan_turn("   ")  # type: ignore[arg-type,return-value]
    with pytest.raises(ApplicationError, match="tool: closed"):
        LiveOrchestrator().execute_turn("not_a_tool", {})


@pytest.mark.skipif(
    os.environ.get("ITAA_AWS_LIVE_TEST") != "1",
    reason="credentialed Bedrock tests require ITAA_AWS_LIVE_TEST=1 and are skipped in CI",
)
def test_credentialed_live_plan_turn_uses_real_model() -> None:
    if os.environ.get("ITAA_AWS_LIVE_INVOKE") != "1":
        pytest.skip("Need ITAA_AWS_LIVE_INVOKE=1 with ITAA_AWS_LIVE_TEST=1")
    os.environ.setdefault("ITAA_AWS_MODEL_MODE", "live")
    os.environ.setdefault("ITAA_AWS_TIMEOUT_MS", "30000")
    model, projection, events = LiveOrchestrator().plan_turn(
        "I'm going away next month and I'll need a car."
    )
    dumped = model.model_dump_json() + projection.model_dump_json() + str(events)
    assert "global.anthropic" not in dumped
    assert "bedrock" not in dumped.lower()
    if model.fallback:
        assert any(event["kind"] == "FALLBACK_DETERMINISTIC" for event in events)
        return
    asked = any(item.id == "dates" for item in model.blockingQuestions)
    assert asked or projection.phase == "clarify"
