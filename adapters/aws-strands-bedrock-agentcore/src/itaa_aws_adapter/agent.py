"""One Buyer Orchestrator. Fake by default. Live never falls back to fake."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from itaa_application.errors import ApplicationError
from itaa_application.golden_path import GoldenPathFacade
from itaa_aws_adapter.events import activity_event
from itaa_aws_adapter.fake import fake_plan_turn
from itaa_aws_adapter.mode import MODE_LIVE, resolve_model_mode
from itaa_aws_adapter.projector import project_plan
from itaa_aws_adapter.schemas import PlanAnswers, PlanProjection, PlanTurn, PlanTurnContext
from itaa_aws_adapter.tools import PLAN_TOOLS, ClosedTools


class Orchestrator(Protocol):
    def plan_turn(
        self,
        objective: str,
        answers: PlanAnswers | None = None,
        context: PlanTurnContext | None = None,
    ) -> tuple[PlanTurn, PlanProjection, list[dict[str, str]]]: ...

    def execute_turn(self, name: str, payload: Mapping[str, object]) -> dict[str, object]: ...


class FakeOrchestrator:
    def __init__(self, facade: GoldenPathFacade | None = None) -> None:
        self._tools = ClosedTools(facade)

    def plan_turn(
        self,
        objective: str,
        answers: PlanAnswers | None = None,
        context: PlanTurnContext | None = None,
    ) -> tuple[PlanTurn, PlanProjection, list[dict[str, str]]]:
        del context
        if not objective.strip():
            raise ApplicationError("objective", "required")
        resolved = answers or PlanAnswers()
        self._tools.call(
            "get_supported_capabilities",
            {},
            turn="plan",
        )
        self._tools.call(
            "project_plan_from_facts",
            {"objective": objective, "answers": resolved.model_dump(mode="json")},
            turn="plan",
        )
        model = fake_plan_turn(objective, resolved)
        projection = project_plan(objective, resolved, model)
        events = [
            activity_event("OBJECTIVE_RECEIVED"),
            activity_event("CHECKING_MISSING"),
        ]
        if projection.phase == "clarify":
            events.append(activity_event("CLARIFICATION_READY"))
        else:
            events.append(activity_event("PLAN_READY", task_count=len(projection.tasks)))
        return model, projection, events

    def execute_turn(self, name: str, payload: Mapping[str, object]) -> dict[str, object]:
        return self._tools.call(name, payload, turn="execute")


class BuyerOrchestrator:
    def __init__(self, inner: Orchestrator) -> None:
        self._inner = inner

    def plan_turn(
        self,
        objective: str,
        answers: PlanAnswers | None = None,
        context: PlanTurnContext | None = None,
    ) -> tuple[PlanTurn, PlanProjection, list[dict[str, str]]]:
        return self._inner.plan_turn(objective, answers, context)

    def execute_turn(self, name: str, payload: Mapping[str, object]) -> dict[str, object]:
        return self._inner.execute_turn(name, payload)


def compose_orchestrator(facade: GoldenPathFacade | None = None) -> BuyerOrchestrator:
    mode = resolve_model_mode()
    if mode == MODE_LIVE:
        from itaa_aws_adapter.live import LiveOrchestrator

        return BuyerOrchestrator(LiveOrchestrator(facade))
    return BuyerOrchestrator(FakeOrchestrator(facade))


def assert_plan_tools_non_mutating() -> tuple[str, ...]:
    return PLAN_TOOLS
