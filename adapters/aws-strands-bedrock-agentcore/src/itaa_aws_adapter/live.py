"""Live Bedrock path. strands is imported only inside this module. Never falls back to fake.

Default live mode stays fail-closed (`model: unavailable`) until
``ITAA_AWS_LIVE_INVOKE=1`` is set for authorized local UAT.
Timeout/schema failures use the labelled deterministic projector, not FakeOrchestrator.
"""

from __future__ import annotations

import concurrent.futures
import json
import sys
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from pydantic import ValidationError

from itaa_application.errors import ApplicationError
from itaa_application.external_search_port import (
    ExperienceSearchPort,
    ExternalSearchPort,
    FlightSearchPort,
)
from itaa_application.golden_path import GoldenPathFacade
from itaa_aws_adapter.events import activity_event
from itaa_aws_adapter.mode import (
    LIVE_SOURCE_REGION,
    live_invoke_authorized,
    resolve_live_model_id,
    resolve_timeout_ms,
)
from itaa_aws_adapter.projector import extract_facts, project_plan, select_clarifications
from itaa_aws_adapter.schemas import PlanAnswers, PlanProjection, PlanTurn, PlanTurnContext
from itaa_aws_adapter.tools import ClosedTools

_SDK_MODULE = "strands"
PlanInvoker = Callable[[str, PlanAnswers, str, int], PlanTurn]

PLAN_SYSTEM = (
    "You are the Reservedge buyer orchestrator. Interpret a free-form travel objective. "
    "Return only the structured PlanTurn schema. Do not approve A1-A4, rank offers, "
    "mint identifiers, or invent airport codes that the human did not state. "
    "blockingQuestions.id must be one of dates, departureAirport, or carNeed. "
    "Leave blockingQuestions empty when parking or rental is an active booking domain; "
    "code asks every remaining catalog-missing parking fact in one buyer message. "
    "If the buyer answers only some of them, the rest are asked together next turn. "
    "Emit requirementPatches for closed catalog fields evidenced in the latest buyer turn. "
    "requirementPatches.kind must be parking or rental. fieldId must be a catalog field. "
    "suggestedTasks.kind must be parking, rental, ents, flight, hotel, or experience. "
    "suggestedTasks.provenance must be explicit, inferred, or proposed. "
    "Mark a task explicit only when the buyer named that component. "
    "Destination and dates alone are not hotel, parking, rental, or experience evidence. "
    "Travelling alone is not experience evidence. Things to do, attractions, activities, "
    "museums, or tours make experience explicit. "
    "If the buyer says flights are already booked, do not search flights. "
    "When a trip is named but no booking component is explicit, ask in buyerSafeMessage "
    "what to book. Invite only currently usable capabilities: hotels, airport parking, "
    "and things to do when experience search is configured. Invite flights when the "
    "buyer asked to fly. Do not offer car rentals as something this build can fulfil. "
    "If the buyer asks to pay for or ticket a flight, say sandbox search is available "
    "but this build does not complete airline payment. "
    "Sandbox search results are not bookings. Changing search dates is not a ticket change. "
    "Do not mention existing tickets, airline payment, or booking platforms unless the "
    "buyer asked to pay or said they already hold a ticket. "
    "Use recentTurns and trusted domain state as memory of this chat. "
    "sessionFacts.tripDates, stayDates, and flightDates are the held windows; "
    "day-only follow-ups keep that month. "
    "When the buyer changes flight dates and hotel or parking is on the plan, ask whether "
    "those dates should follow. Keep buyerSafeMessage to one or two short sentences. "
    "No markdown, no emoji, no queued-search summaries. Code dispatches search. "
    "Code may re-search after an explicit date change; do not ask to re-authorize that search. "
    "If destination is already named, do not ask where. If dates are already named, do not "
    "ask when. Ask only for the missing fact. "
    "Do not emit a helpWith blocking question. Do not invent a vertical. "
    "Evidence spans must be character offsets in the objective or answers. "
    "Copy calendar years from the objective or answers only when the buyer typed a year. "
    "If the buyer omitted a year, trusted code assigns the nearest future occurrence from today. "
    "Never emit a past year for an ordinary prospective booking. "
    "Set fallback to false when returning a valid PlanTurn. "
    "Buyer-safe copy only. Temperature is low; do not speculate. "
    "Trip departure, trip destination, and parking airport are distinct. "
    "Do not copy Mumbai or New York into parking. Do not invent JFK. "
    "Do not infer a parking airport from a multi-airport city such as London or New York. "
    "If a city has exactly one supported airport (Manchester→MAN, Edinburgh→EDI), resolve "
    "it without asking which airport. Accept IATA codes in any case, including man→MAN. "
    "Heathrow normalizes to LHR only as an approved named airport. "
    "Do not re-ask facts already present in trusted domain state. "
    "Do not ask parking vehicle class; that is a rental-car fact. "
    "Parking vehicleClass defaults in code unless the buyer named a class. "
    "'I don't need covered parking' is covered=none, not preferred. "
    "Parking start and end require buyer clock times. Do not invent noon, midnight, or 12:00Z. "
    "Do not treat a rental-car or entertainment request as airport parking. "
    "Do not treat a dated destination trip as automatic hotel search, experience search, "
    "or airport parking. "
    "Do not invent JFK. Do not copy Mumbai, Milan, London, or New York into parking. "
    "Provider search waits for a typed pending search authorization after requirements "
    "are complete. Do not claim a search has run, and do not invent offer counts. "
    "Fill facts.destination with the named city even when it is uncommon. "
    "Fill facts.startDate and facts.endDate as ISO dates when the buyer named a stay window. "
    "Do not restrict destinations to a city list. "
    "Ask every remaining material missing parking fact in one buyer-safe message. "
    "Do not claim offers "
    "are ready, ranked, selected, or refreshed before authorized supplier solicitation. "
    "When lastAgentMessage asked which airports to search for the flight booking, "
    "interpret the latest buyer message against that flight-airport question. Short "
    "replies such as all, those, either, any, "
    "both, everywhere, or all airports mean search every supported airport in the two "
    "named cities: fill facts.departureAirport and facts.destinationAirport with those "
    "city metro codes (Dubai=DXB, London=LON, New York=NYC). Named IATA or airport "
    "names from the offered pair are explicit origin/destination. Do not leave those "
    "facts empty when the buyer answered the airport question. Do not invent codes for "
    "a city that was not named, and do not copy a parking airport into origin."
)
_INVOKE_STATS: list[dict[str, object]] = []


def consume_invoke_stats() -> list[dict[str, object]]:
    """Operator UAT metrics. Never attached to buyer PlanTurn or projection JSON."""

    out = list(_INVOKE_STATS)
    _INVOKE_STATS.clear()
    return out


def _record_invoke_stats(result: Any) -> None:
    metrics = getattr(result, "metrics", None)
    usage = getattr(metrics, "accumulated_usage", None) if metrics is not None else None
    latency = getattr(metrics, "accumulated_metrics", None) if metrics is not None else None
    stats: dict[str, object] = {
        "stopReason": getattr(result, "stop_reason", None),
        "modelId": resolve_live_model_id(),
        "region": LIVE_SOURCE_REGION,
        "provider": "amazon-bedrock",
        "sdk": _SDK_MODULE,
    }
    if isinstance(usage, dict):
        stats["inputTokens"] = usage.get("inputTokens")
        stats["outputTokens"] = usage.get("outputTokens")
        stats["totalTokens"] = usage.get("totalTokens")
    if isinstance(latency, dict):
        stats["latencyMs"] = latency.get("latencyMs")
    cycle_count = getattr(metrics, "cycle_count", None) if metrics is not None else None
    if isinstance(cycle_count, int):
        stats["cycleCount"] = cycle_count
    _INVOKE_STATS.append(stats)
    sys.stderr.write(
        "itaa_live_plan "
        f"fallback=false cycles={stats.get('cycleCount')} "
        f"latencyMs={stats.get('latencyMs')} "
        f"tokens={stats.get('inputTokens')}/{stats.get('outputTokens')}/"
        f"{stats.get('totalTokens')}\n"
    )


def _first_cycle_structured_output_context() -> type:
    """Strands context that requires PlanTurn on the first model cycle."""

    from strands.tools.structured_output._structured_output_context import (
        StructuredOutputContext,
    )

    class FirstCycleStructuredOutputContext(StructuredOutputContext):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self.set_forced_mode()

    return FirstCycleStructuredOutputContext


@contextmanager
def _force_first_cycle_structured_output() -> Iterator[None]:
    """Patch only the Agent constructor lookup used by this live plan invoke."""

    from strands.agent import agent as strands_agent

    forced = _first_cycle_structured_output_context()
    original = strands_agent.StructuredOutputContext  # type: ignore[attr-defined]
    strands_agent.StructuredOutputContext = forced  # type: ignore[attr-defined, assignment]
    try:
        yield
    finally:
        strands_agent.StructuredOutputContext = original  # type: ignore[attr-defined]


def live_runtime_ready() -> bool:
    try:
        resolve_live_model_id()
        resolve_timeout_ms()
    except ApplicationError:
        return False
    try:
        __import__(_SDK_MODULE)
    except ImportError:
        return False
    return True


def _fallback_turn(objective: str, answers: PlanAnswers) -> PlanTurn:
    facts = extract_facts(objective, answers)
    questions = select_clarifications(facts)
    return PlanTurn(
        understanding="Using the local planner (labelled).",
        facts=facts,
        evidence=[],
        blockingQuestions=questions,
        suggestedTasks=[],
        buyerSafeMessage="Using the local planner (labelled).",
        fallback=True,
    )


def _events_for(projection: PlanProjection, *, fallback: bool) -> list[dict[str, str]]:
    events = [
        activity_event("OBJECTIVE_RECEIVED"),
        activity_event("CHECKING_MISSING"),
    ]
    if fallback:
        events.append(activity_event("FALLBACK_DETERMINISTIC"))
    if projection.phase == "clarify":
        events.append(activity_event("CLARIFICATION_READY"))
    else:
        events.append(activity_event("PLAN_READY", task_count=len(projection.tasks)))
    return events


def _invoke_strands_plan(
    objective: str,
    answers: PlanAnswers,
    model_id: str,
    timeout_ms: int,
    context: PlanTurnContext | None = None,
) -> PlanTurn:
    from botocore.config import Config as BotocoreConfig  # type: ignore[import-untyped]
    from strands import Agent
    from strands.models.bedrock import BedrockModel
    from strands.types.exceptions import StructuredOutputException

    from itaa_api.agent_requirements import catalog_prompt

    timeout_s = max(1, int(timeout_ms / 1000))
    model = BedrockModel(
        model_id=model_id,
        region_name=LIVE_SOURCE_REGION,
        temperature=0.3,
        streaming=False,
        boto_client_config=BotocoreConfig(
            read_timeout=timeout_s,
            connect_timeout=min(10, timeout_s),
            retries={"max_attempts": 1, "mode": "standard"},
            user_agent_extra="itaa-aws-adapter",
        ),
    )
    resolved_context = context or PlanTurnContext()
    latest = resolved_context.lastUserMessage.strip() or "(session start)"
    trusted_raw = (
        resolved_context.trustedDomains if isinstance(resolved_context.trustedDomains, dict) else {}
    )
    last_agent = str(trusted_raw.get("lastAgentMessage") or "").strip()
    history = json.dumps(trusted_raw.get("recentTurns") or [], default=str)
    trusted = json.dumps(trusted_raw, default=str)
    prompt = (
        f"Objective / conversation:\n{objective.strip()}\n\n"
        f"Current chat (oldest to newest):\n{history}\n\n"
        f"Latest buyer message:\n{latest}\n\n"
        f"Previous assistant message:\n{last_agent or '(none)'}\n\n"
        f"Trusted domain state JSON:\n{trusted}\n\n"
        f"Structured answers JSON:\n{answers.model_dump_json()}\n\n"
        f"{catalog_prompt()}\n"
        "Propose closed RequirementPatch values. Code validates before trusted state changes. "
        "Never invent JFK from New York. Never copy London into parking.airportCode. "
        "If the previous assistant message asked which airports to search, fill "
        "facts.departureAirport and facts.destinationAirport from this buyer reply.\n"
    )

    def _call() -> Any:
        with _force_first_cycle_structured_output():
            agent = Agent(
                model=model,
                tools=[],
                system_prompt=PLAN_SYSTEM,
                structured_output_model=PlanTurn,
                callback_handler=None,
                load_tools_from_directory=False,
            )
            return agent(prompt, structured_output_model=PlanTurn)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_call)
        try:
            result = future.result(timeout=timeout_s)
        except concurrent.futures.TimeoutError as exc:
            future.cancel()
            raise TimeoutError("live plan deadline exceeded") from exc
        except StructuredOutputException as exc:
            raise ApplicationError("model", "schema_invalid") from exc
        except Exception as exc:
            from botocore.exceptions import ClientError  # type: ignore[import-untyped]

            if isinstance(exc, ClientError):
                raise ApplicationError("model", "unavailable") from exc
            raise
    _record_invoke_stats(result)
    parsed = getattr(result, "structured_output", None)
    if isinstance(parsed, PlanTurn):
        return parsed
    if isinstance(parsed, Mapping):
        return PlanTurn.model_validate(parsed)
    raise ApplicationError("model", "schema_invalid")


class LiveOrchestrator:
    """Fail-closed unless invoke is authorized for local UAT."""

    def __init__(
        self,
        facade: GoldenPathFacade | None = None,
        *,
        plan_invoker: PlanInvoker | None = None,
        stay_search: ExternalSearchPort | None = None,
        experience_search: ExperienceSearchPort | None = None,
        flight_search: FlightSearchPort | None = None,
    ) -> None:
        resolve_live_model_id()
        resolve_timeout_ms()
        self._tools = ClosedTools(
            facade,
            stay_search=stay_search,
            experience_search=experience_search,
            flight_search=flight_search,
        )
        self._plan_invoker = plan_invoker
        self.last_plan_turn: PlanTurn | None = None
        self._context = PlanTurnContext()

    def plan_turn(
        self,
        objective: str,
        answers: PlanAnswers | None = None,
        context: PlanTurnContext | None = None,
    ) -> tuple[PlanTurn, PlanProjection, list[dict[str, str]]]:
        if not objective.strip():
            raise ApplicationError("objective", "required")
        if not live_invoke_authorized():
            raise ApplicationError("model", "unavailable")
        resolved = answers or PlanAnswers()
        self._context = context or PlanTurnContext()
        self._tools.call("get_supported_capabilities", {}, turn="plan")
        self._tools.call(
            "project_plan_from_facts",
            {"objective": objective, "answers": resolved.model_dump(mode="json")},
            turn="plan",
        )
        model_id = resolve_live_model_id()
        timeout_ms = resolve_timeout_ms()
        fallback = False
        try:
            if self._plan_invoker is None:
                model = _invoke_strands_plan(
                    objective, resolved, model_id, timeout_ms, self._context
                )
            else:
                model = self._plan_invoker(objective, resolved, model_id, timeout_ms)
            model = PlanTurn.model_validate(model.model_dump(mode="json"))
        except (TimeoutError, ValidationError):
            model = _fallback_turn(objective, resolved)
            fallback = True
        except ApplicationError as exc:
            if exc.code != "schema_invalid":
                raise
            model = _fallback_turn(objective, resolved)
            fallback = True
        if model.fallback:
            fallback = True
        if fallback:
            sys.stderr.write("itaa_live_plan fallback=true\n")
        projection = project_plan(objective, resolved, model)
        self.last_plan_turn = model
        return model, projection, _events_for(projection, fallback=fallback)

    def execute_turn(self, name: str, payload: Mapping[str, object]) -> dict[str, object]:
        if not live_invoke_authorized():
            raise ApplicationError("model", "unavailable")
        return self._tools.call(name, payload, turn="execute")
