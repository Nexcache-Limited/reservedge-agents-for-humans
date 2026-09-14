"""Provider-neutral agent-session BFF.

Fake model mode plans in-process and never requires Bedrock or an adapter listener.
Live split topology still HTTP-forwards to /v1/aws/** only.

Browser product path is /v1/agent/**. This module must not import strands, boto3,
botocore, Bedrock, or AgentCore. Raw objective text stays session-local.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator, Mapping, MutableMapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, Protocol, cast

from fastapi import APIRouter, Body, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from itaa_api.agent_requirements import (
    AIRPORT_CHOICE_LABELS,
    CLOCK_SPAN_RE,
    COMPETITION_PARKING_ONLY_COPY,
    FLIGHT_UNSUPPORTED_COPY,
    IATA_STAY_PLACE,
    KNOWN_IATA,
    RENTAL_NO_ADAPTER_COPY,
    airport_candidates_for_city,
    apply_defaults,
    apply_model_patches,
    apply_patch,
    date_mutation_without_calendar,
    empty_domain,
    execution_fields,
    extract_conversation_patches,
    join_catalog_asks,
    keep_existing_clock,
    mark_stale,
    normalize_iata,
    overlay_calendar_on_instant,
    overlay_time_on_instant,
    parking_airport_ask,
    public_domain,
    refresh_completeness,
    resolve_airport_reply,
    sanitize_buyer_message,
    single_city_airport,
)
from itaa_api.calendar_resolve import parse_parking_clock_window, rewrite_past_iso_if_year_omitted
from itaa_api.conversation_refine import (
    BuyerRefinement,
    bind_day_shift,
    cascade_copy,
    is_explicit_date_mutation,
    parse_date_cascade_reply,
    parse_refinement,
    refinement_copy,
)
from itaa_api.errors import (
    application_error_handler,
    http_exception_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from itaa_api.intake import (
    IntakeAcceptanceBody,
    IntakeAuthorizationBody,
    IntakeGateBody,
    accept_intake_intent,
    authorize_intake_intent,
    confirm_intake_intent,
    create_owned_parking_intent,
    dispatch_intake_intent,
    get_intake_intent,
    register_agent_intake,
)
from itaa_api.portfolio_http import attach_portfolio_cookie
from itaa_api.search_authorization import (
    EXPERIENCE as SEARCH_EXPERIENCE,
)
from itaa_api.search_authorization import (
    FLIGHT as SEARCH_FLIGHT,
)
from itaa_api.search_authorization import (
    PARKING as SEARCH_PARKING,
)
from itaa_api.search_authorization import (
    STAY as SEARCH_STAY,
)
from itaa_api.search_authorization import (
    build_pending,
    fingerprints_match,
    flight_requested,
    match_confirmation,
    public_pending,
    results_copy,
)
from itaa_application.capability_routing import (
    Capability,
    established_capabilities,
    snapshots_from_projection,
)
from itaa_application.errors import ApplicationError
from itaa_application.golden_path import GoldenPathFacade

PREFIX = "/v1/agent"
AWS_PLAN_PATH = "/v1/aws/plan-turns"
AWS_EXECUTE_PATH = "/v1/aws/execute-turns"
DEFAULT_ADAPTER_URL = "http://127.0.0.1:8080"
SESSION_PATTERN = re.compile(r"^as_[0-9a-hjkmnp-tv-z]{26}$")
CORRELATION_PATTERN = re.compile(r"^cr_[0-9a-hjkmnp-tv-z]{26}$")
_CROCKFORD = "0123456789abcdefghjkmnpqrstvwxyz"
_HANDOFF_KEYS = (
    "airportCode",
    "start",
    "end",
    "startDate",
    "endDate",
    "vehicleClass",
    "covered",
    "shuttleMaxMinutes",
    "currency",
    "accessibility",
    "intakeId",
)
_ANSWER_KEYS = ("departureAirport", "carNeed", "helpWith", "dates", "startDate", "endDate")
_CAPABILITY_TOOLS: dict[Capability, str] = {
    Capability.STAY_SEARCH: "search_stay_offers",
    Capability.EXPERIENCE_SEARCH: "search_experience_offers",
}
_TIMEOUT_MIN_MS = 5000
_TIMEOUT_MAX_MS = 45000
_FAKE_TIMEOUT_S = 5.0
_TIMEOUT_MARGIN_S = 5.0
_PREPARE_TOOL = "prepare_parking_requirement"
_MUTATING_TOOLS = frozenset(
    {
        "solicit_parking_offers",
        "accept_offer",
        "authorize_simulated_transaction",
    }
)
PARKING_INTAKE_PATH = "/intents/new/parking"
FALLBACK_COPY = "Using the local planner (labelled)"
FAILED_COPY = "Could not complete this step"
CONFIRMED_COPY = "Plan confirmed"

router = APIRouter()


class AwsProvider(Protocol):
    def plan_turn(self, payload: Mapping[str, object]) -> dict[str, object]: ...

    def execute_turn(self, payload: Mapping[str, object]) -> dict[str, object]: ...


class SessionCreateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    objective: str
    correlationId: str | None = Field(default=None, pattern="^cr_[0-9a-hjkmnp-tv-z]{26}$")


class SessionTurnBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answers: dict[str, Any] | None = None
    message: str | None = None
    tool: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    patches: list[dict[str, Any]] | None = None
    correlationId: str | None = Field(default=None, pattern="^cr_[0-9a-hjkmnp-tv-z]{26}$")


class SessionGrantBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gate: Literal["A1", "A2", "A3", "A4"]
    domain: Literal["parking"] = "parking"
    offerId: str | None = None
    offerVersion: int | None = Field(default=None, ge=1)
    confirm: Literal[True] | None = None


class SessionConfirmBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: Literal[True] | None = None


@dataclass
class AgentSession:
    session_id: str
    objective: str
    answers: dict[str, str]
    extra_note: str = ""
    provider_phase: str = "clarify"
    confirmed: bool = False
    fallback: bool = False
    projection: dict[str, object] = field(default_factory=dict)
    events: list[dict[str, object]] = field(default_factory=list)
    tool_trace: list[dict[str, object]] = field(default_factory=list)
    pending_authorizations: list[dict[str, object]] = field(default_factory=list)
    pending_authorization: dict[str, object] | None = None
    parking_handoff: dict[str, object] | None = None
    correlation_id: str = ""
    transcript: list[dict[str, object]] = field(default_factory=list)
    domains: dict[str, dict[str, object]] = field(default_factory=dict)
    buyer_safe_message: str = ""
    stay_search: dict[str, object] | None = None
    stay_search_fingerprint: str = ""
    stay_rate_refs: dict[str, str] = field(default_factory=dict)
    experience_search: dict[str, object] | None = None
    experience_search_fingerprint: str = ""
    pending_search_authorization: dict[str, object] | None = None
    stay_max_amount_minor: int | None = None
    locked_destination: str = ""
    locked_origin: str = ""
    dropped_kinds: list[str] = field(default_factory=list)
    parking_dates_held: bool = False
    locked_parking_start: str = ""
    locked_parking_end: str = ""
    flight_search: dict[str, object] | None = None
    flight_search_fingerprint: str = ""
    flight_prefs_resolved: bool = False
    flight_airports_resolved: bool = False
    last_refinement_note: str = ""
    pending_date_cascade: dict[str, object] | None = None
    last_revised_kind: str = ""
    search_execution: list[dict[str, object]] = field(default_factory=list)
    flight_draft_end: str = ""
    stay_draft_start: str = ""
    stay_draft_end: str = ""
    auto_search: list[str] = field(default_factory=list)


def mint_opaque(prefix: str) -> str:
    raw = secrets.token_bytes(26)
    return prefix + "".join(_CROCKFORD[byte % 32] for byte in raw)


def adapter_base_url(raw: str | None = None) -> str:
    text = DEFAULT_ADAPTER_URL if raw is None else raw
    if raw is None:
        text = os.environ.get("ITAA_AWS_ADAPTER_URL", DEFAULT_ADAPTER_URL)
    base = text.strip().rstrip("/")
    if base == "":
        base = DEFAULT_ADAPTER_URL
    if "/v1/agent" in base.lower():
        raise ApplicationError("internal", "closed")
    return base


def bff_timeout_s() -> float:
    raw = os.environ.get("ITAA_AWS_TIMEOUT_MS")
    if raw is None or raw.strip() == "":
        return _FAKE_TIMEOUT_S
    try:
        value = int(raw.strip())
    except ValueError:
        raise ApplicationError("model", "schema_invalid") from None
    if value < _TIMEOUT_MIN_MS or value > _TIMEOUT_MAX_MS:
        raise ApplicationError("model", "schema_invalid")
    return value / 1000.0 + _TIMEOUT_MARGIN_S


def build_agent_app(
    provider: AwsProvider | None = None,
    facade: GoldenPathFacade | None = None,
) -> FastAPI:
    application = FastAPI(title="ITAA agent session", docs_url=None, redoc_url=None)
    application.state.aws_provider = provider
    application.state.agent_sessions = {}
    if facade is not None:
        application.state.facade = facade
    if provider is None:
        attach_default_plan_provider(application)
    application.include_router(router)
    application.add_exception_handler(ApplicationError, application_error_handler)  # type: ignore[arg-type]
    application.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    application.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    application.add_exception_handler(Exception, unhandled_error_handler)
    attach_portfolio_cookie(application)
    return application


class HttpAwsProvider:
    """POST /v1/aws/plan-turns and /v1/aws/execute-turns only. Never /v1/agent/**."""

    def plan_turn(self, payload: Mapping[str, object]) -> dict[str, object]:
        return _http_post(AWS_PLAN_PATH, payload)

    def execute_turn(self, payload: Mapping[str, object]) -> dict[str, object]:
        return _http_post(AWS_EXECUTE_PATH, payload)


class _InProcessFakeProvider:
    """Same-process fake Plan/Execute. Never HTTP, Bedrock, or adapter loopback."""

    def __init__(self, orchestrator: Any) -> None:
        self._orchestrator = orchestrator

    def plan_turn(self, payload: Mapping[str, object]) -> dict[str, object]:
        from itaa_aws_adapter.schemas import PlanAnswers, PlanTurnContext

        raw_answers = payload.get("answers")
        answers = PlanAnswers.model_validate(raw_answers if isinstance(raw_answers, dict) else {})
        objective = str(payload.get("objective") or "")
        raw_trusted = payload.get("trustedDomains")
        context = PlanTurnContext(
            lastUserMessage=str(payload.get("lastUserMessage") or ""),
            trustedDomains=raw_trusted if isinstance(raw_trusted, dict) else {},
        )
        model, projection, events = self._orchestrator.plan_turn(objective, answers, context)
        return {
            "planTurn": model.model_dump(mode="json"),
            "projection": projection.model_dump(mode="json"),
            "events": events,
            "correlationId": payload.get("correlationId"),
        }

    def execute_turn(self, payload: Mapping[str, object]) -> dict[str, object]:
        tool = str(payload.get("tool") or "")
        inner = payload.get("payload")
        result = self._orchestrator.execute_turn(tool, inner if isinstance(inner, dict) else {})
        return {
            "tool": tool,
            "result": result,
            "correlationId": payload.get("correlationId"),
        }


def _model_mode_is_live() -> bool:
    raw = os.environ.get("ITAA_AWS_MODEL_MODE", "").strip().lower()
    if raw == "live":
        return True
    return raw == "" and os.environ.get("ITAA_AWS_LIVE") == "1"


def _explicit_adapter_url() -> bool:
    return os.environ.get("ITAA_AWS_ADAPTER_URL", "").strip() != ""


def _should_use_in_process_fake() -> bool:
    if _model_mode_is_live() or _explicit_adapter_url():
        return False
    raw = os.environ.get("ITAA_AWS_MODEL_MODE", "").strip().lower()
    return raw in {"", "fake"}


def _build_fake_in_process_provider(facade: GoldenPathFacade | None) -> AwsProvider | None:
    try:
        from itaa_aws_adapter.agent import compose_orchestrator
    except ImportError:
        return None
    return _InProcessFakeProvider(compose_orchestrator(facade=facade))


def attach_default_plan_provider(application: FastAPI) -> None:
    """Inject the credential-free fake orchestrator when the BFF is started alone."""

    if getattr(application.state, "aws_provider", None) is not None:
        return
    if not _should_use_in_process_fake():
        return
    facade = getattr(application.state, "facade", None)
    provider = _build_fake_in_process_provider(
        facade if isinstance(facade, GoldenPathFacade) else None
    )
    if provider is not None:
        application.state.aws_provider = provider


def _http_post(path: str, payload: Mapping[str, object]) -> dict[str, object]:
    if path not in {AWS_PLAN_PATH, AWS_EXECUTE_PATH}:
        raise ApplicationError("internal", "closed")
    if path.startswith(PREFIX) or "/v1/agent" in path:
        raise ApplicationError("internal", "closed")
    target = f"{adapter_base_url()}{path}"
    parsed = urllib.parse.urlparse(target)
    if "/v1/agent" in parsed.path or "/v1/agent" in target.lower():
        raise ApplicationError("internal", "closed")
    request = urllib.request.Request(
        target,
        data=json.dumps(dict(payload)).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=bff_timeout_s()) as response:
            parsed_json = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise _closed_http_error(exc) from None
    except (
        urllib.error.URLError,
        TimeoutError,
        json.JSONDecodeError,
        OSError,
    ):
        raise ApplicationError("model", "unavailable") from None
    if not isinstance(parsed_json, dict):
        raise ApplicationError("model", "unavailable")
    return parsed_json


def _closed_http_error(exc: urllib.error.HTTPError) -> ApplicationError:
    try:
        body = json.loads(exc.read().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return ApplicationError("model", "unavailable")
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        field = error.get("field")
        code = error.get("code")
        if isinstance(field, str) and isinstance(code, str) and field and code:
            return ApplicationError(field, code)
    return ApplicationError("model", "unavailable")


def _sessions(request: Request) -> MutableMapping[str, AgentSession]:
    store = getattr(request.app.state, "agent_sessions", None)
    if store is None:
        request.app.state.agent_sessions = {}
        store = request.app.state.agent_sessions
    if not isinstance(store, dict):
        raise ApplicationError("internal", "closed")
    return store


def _provider(request: Request) -> AwsProvider:
    injected = getattr(request.app.state, "aws_provider", None)
    if injected is not None:
        return cast(AwsProvider, injected)
    attach_default_plan_provider(request.app)
    attached = getattr(request.app.state, "aws_provider", None)
    if attached is not None:
        return cast(AwsProvider, attached)
    return HttpAwsProvider()


def _session_id(raw: str) -> str:
    if not isinstance(raw, str) or not SESSION_PATTERN.fullmatch(raw):
        raise ApplicationError("sessionId", "invalid_opaque_syntax")
    return raw


def _require_session(request: Request, raw: str) -> AgentSession:
    session_id = _session_id(raw)
    session = _sessions(request).get(session_id)
    if session is None:
        raise ApplicationError("sessionId", "unknown_resource")
    return session


def _correlation(raw: str | None) -> str:
    if raw is None or raw == "":
        return mint_opaque("cr_")
    if not CORRELATION_PATTERN.fullmatch(raw):
        raise ApplicationError("correlationId", "invalid_opaque_syntax")
    return raw


def _merge_answers(current: Mapping[str, str], incoming: Mapping[str, object]) -> dict[str, str]:
    merged = dict(current)
    for key in _ANSWER_KEYS:
        value = incoming.get(key)
        if isinstance(value, str) and value.strip():
            merged[key] = value.strip()
    return merged


def _provider_objective(session: AgentSession) -> str:
    parts = [session.objective.strip()]
    if session.extra_note.strip():
        parts.append(session.extra_note.strip())
    return " ".join(item for item in parts if item)


def _session_refinement(session: AgentSession) -> BuyerRefinement | None:
    last = _last_user_text(session)
    if not last:
        return None
    parking = session.domains.get("parking")
    parking_authorized = isinstance(parking, dict) and parking.get("completeness") == "authorized"
    stay_start, stay_end = _stay_window(session)
    flight_start = _flight_field(session, "date")
    flight_end = _flight_field(session, "dateEnd") or session.flight_draft_end
    answers_start = str(session.answers.get("startDate") or "")
    answers_end = str(session.answers.get("endDate") or "")
    return bind_day_shift(
        parse_refinement(last),
        stay_start=stay_start or answers_start,
        stay_end=stay_end or answers_end,
        parking_authorized=parking_authorized,
        last_text=last,
        flight_start=flight_start or answers_start,
        flight_end=flight_end or answers_end,
    )


def _revised_kind(change: BuyerRefinement) -> str:
    if (
        change.date_scope == "flight"
        or change.flight_origin
        or change.flight_destination
        or change.flight_date
    ):
        return "flight"
    if change.date_scope == "stay" or change.destination or change.stay_max_minor is not None:
        return "hotel"
    if change.date_scope == "parking" or change.parking_airport:
        return "parking"
    if change.add_experience:
        return "experience"
    return "trip"


def _apply_conversation_refinements(session: AgentSession) -> None:
    last = _last_user_text(session)
    if not last:
        return
    if _apply_date_cascade_reply(session, last):
        return
    change = _session_refinement(session)
    if change is None or not change.applies():
        return
    had_results = _domain_has_search_results(session, change)
    mutated_dates = (
        bool(change.start_date)
        and bool(change.end_date)
        and is_explicit_date_mutation(last, change)
    )
    auto_search: list[str] = []
    if mutated_dates and change.date_scope == "stay" and session.stay_search is not None:
        auto_search = [SEARCH_STAY]
    elif mutated_dates and change.date_scope == "all" and not _is_opening_intent_turn(session):
        kinds: set[str] = set()
        if session.flight_search is not None:
            start_date = change.start_date
            end_date = change.end_date
            if start_date is not None and end_date is not None:
                _apply_flight_date_draft(session, start_date, end_date)
            kinds.add("flight")
        if session.stay_search is not None:
            kinds.add("stay")
        kinds.add("parking")
        auto_search = _inventory_search_caps(session, kinds=kinds)
    note = refinement_copy(change, had_results=had_results and not auto_search)
    if _is_opening_intent_turn(session) and not is_explicit_date_mutation(last, change):
        note = ""
    if change.start_date and change.end_date and is_explicit_date_mutation(last, change):
        if change.date_scope == "all":
            session.answers["startDate"] = change.start_date
            session.answers["endDate"] = change.end_date
            session.answers["dates"] = f"{change.start_date} to {change.end_date}"
            session.stay_draft_start = change.start_date
            session.stay_draft_end = change.end_date
            session.parking_dates_held = False
        elif change.date_scope == "stay":
            session.stay_draft_start = change.start_date
            session.stay_draft_end = change.end_date
    if change.destination:
        session.locked_destination = change.destination
    if change.flight_origin:
        session.locked_origin = change.flight_origin_place or change.flight_origin
        session.answers["departureAirport"] = change.flight_origin
    if change.stay_max_minor is not None:
        session.stay_max_amount_minor = change.stay_max_minor
    if change.hold_parking_dates:
        session.parking_dates_held = True
    if change.drop_parking and "parking" not in session.dropped_kinds:
        session.dropped_kinds.append("parking")
    if change.add_experience and "things to do" not in session.extra_note.lower():
        session.extra_note = f"{session.extra_note} things to do".strip()
    parking = session.domains.get("parking")
    if isinstance(parking, dict) and not session.parking_dates_held and change.parking_airport:
        apply_patch(
            parking,
            "airportCode",
            change.parking_airport,
            source="current_turn",
            provenance="explicit",
        )
        mark_stale(parking, ["airportCode"])
    if change.flight_origin or change.flight_destination or change.flight_date:
        _ensure_flight_domain(session)
        flight = session.domains["flight"]
        fields = flight.setdefault("fields", {})
        if not isinstance(fields, dict):
            fields = {}
            flight["fields"] = fields
        flight["accepted"] = True
        flight["provenance"] = "explicit"
        if change.flight_origin:
            fields["origin"] = {
                "value": change.flight_origin,
                "source": "current_turn",
                "provenance": "explicit",
            }
            facts = session.projection.get("facts") if isinstance(session.projection, dict) else {}
            if isinstance(facts, dict):
                facts["departureAirport"] = change.flight_origin
                if change.flight_origin_place:
                    facts["originCity"] = change.flight_origin_place
            dest = _flight_field(session, "destination")
            if change.flight_origin and dest:
                session.flight_airports_resolved = True
        if change.flight_destination:
            fields["destination"] = {
                "value": change.flight_destination,
                "source": "current_turn",
                "provenance": "explicit",
            }
        if change.flight_date:
            fields["date"] = {
                "value": change.flight_date,
                "source": "current_turn",
                "provenance": "explicit",
            }
    if (
        change.date_scope == "flight"
        and change.start_date
        and change.end_date
        and is_explicit_date_mutation(last, change)
        and not _is_opening_intent_turn(session)
    ):
        _apply_flight_date_draft(session, change.start_date, change.end_date)
        original_start = str(session.answers.get("startDate") or "")
        original_end = str(session.answers.get("endDate") or "")
        facts = session.projection.get("facts") if isinstance(session.projection, dict) else {}
        if isinstance(facts, dict):
            original_start = original_start or str(facts.get("startDate") or "")
            original_end = original_end or str(facts.get("endDate") or "")
        session.pending_date_cascade = {
            "source": "flight",
            "start": change.start_date,
            "end": change.end_date,
            "originalStart": original_start,
            "originalEnd": original_end,
        }
        note = cascade_copy(change, original_start=original_start, original_end=original_end)
        auto_search = []
    session.last_refinement_note = note
    if _is_opening_intent_turn(session) and not is_explicit_date_mutation(last, change):
        session.last_revised_kind = ""
    else:
        session.last_revised_kind = _revised_kind(change)
    session.pending_search_authorization = None
    session.auto_search = auto_search
    _overlay_parking_dates(session, change)


def _ensure_flight_domain(session: AgentSession) -> None:
    flight = session.domains.get("flight")
    if not isinstance(flight, dict):
        session.domains["flight"] = empty_domain("flight", provenance="explicit", accepted=True)


def _apply_flight_date_draft(session: AgentSession, start: str, end: str) -> None:
    _ensure_flight_domain(session)
    flight = session.domains["flight"]
    flight["accepted"] = True
    fields = flight.setdefault("fields", {})
    if not isinstance(fields, dict):
        fields = {}
        flight["fields"] = fields
    fields["date"] = {"value": start[:10], "source": "current_turn", "provenance": "explicit"}
    fields["dateEnd"] = {"value": end[:10], "source": "current_turn", "provenance": "explicit"}
    session.flight_draft_end = end[:10]


def _domain_has_search_results(session: AgentSession, change: BuyerRefinement) -> bool:
    stay_ok = (
        isinstance(session.stay_search, dict)
        and session.stay_search.get("status") == "ok"
        and bool(session.stay_search.get("offers"))
    )
    flight_ok = (
        isinstance(session.flight_search, dict)
        and session.flight_search.get("status") == "ok"
        and bool(session.flight_search.get("offers"))
    )
    parking = session.domains.get("parking")
    parking_ok = False
    if isinstance(parking, dict):
        offer = parking.get("offerSet")
        snapshot = offer.get("snapshot") if isinstance(offer, dict) else None
        offers = snapshot.get("offers") if isinstance(snapshot, dict) else None
        parking_ok = isinstance(offers, list) and bool(offers)
    if change.date_scope == "stay":
        return stay_ok
    if change.date_scope == "parking":
        return parking_ok
    if (
        change.date_scope == "flight"
        or change.flight_origin
        or change.flight_destination
        or change.flight_date
    ):
        return flight_ok
    return stay_ok or flight_ok or parking_ok


def _apply_date_cascade_reply(session: AgentSession, last: str) -> bool:
    pending = session.pending_date_cascade
    if not isinstance(pending, dict):
        return False
    decision = parse_date_cascade_reply(last)
    if decision is None:
        return False
    session.pending_date_cascade = None
    if decision == "hold":
        session.last_refinement_note = "Hotel and parking stay on the original dates."
        session.last_revised_kind = "flight"
        session.pending_search_authorization = None
        session.auto_search = _inventory_search_caps(session, kinds={"flight"})
        return True
    start = str(pending.get("start") or "")
    end = str(pending.get("end") or "")
    if start and end:
        session.answers["startDate"] = start
        session.answers["endDate"] = end
        session.answers["dates"] = f"{start} to {end}"
        session.stay_draft_start = start
        session.stay_draft_end = end
        _overlay_parking_dates(
            session,
            BuyerRefinement(start_date=start, end_date=end, date_scope="all"),
            force=True,
        )
    session.last_refinement_note = "I've updated the hotel and parking to follow the flight dates."
    session.last_revised_kind = "trip"
    session.pending_search_authorization = None
    session.auto_search = _inventory_search_caps(session, kinds={"flight", "stay", "parking"})
    return True


def _inventory_search_caps(session: AgentSession, *, kinds: set[str]) -> list[str]:
    caps: list[str] = []
    if "flight" in kinds and session.flight_search is not None:
        caps.append(SEARCH_FLIGHT)
    if "stay" in kinds and session.stay_search is not None:
        caps.append(SEARCH_STAY)
    if "parking" in kinds:
        parking = session.domains.get("parking")
        offer = parking.get("offerSet") if isinstance(parking, dict) else None
        snapshot = offer.get("snapshot") if isinstance(offer, dict) else None
        offers = snapshot.get("offers") if isinstance(snapshot, dict) else None
        if isinstance(offers, list) and offers:
            caps.append(SEARCH_PARKING)
    return caps


def _reapply_last_date_refinement(session: AgentSession) -> None:
    last = _last_user_text(session)
    if last:
        change = _session_refinement(session)
        if change is not None and change.start_date:
            _overlay_parking_dates(session, change)
    if (
        session.locked_parking_start
        and session.locked_parking_end
        and not session.parking_dates_held
        and "parking" not in session.dropped_kinds
    ):
        parking = session.domains.get("parking")
        if not isinstance(parking, dict):
            return
        fields = parking.get("fields") if isinstance(parking.get("fields"), dict) else {}
        current_start = None
        current_end = None
        if isinstance(fields, dict):
            held_start = fields.get("start")
            held_end = fields.get("end")
            if isinstance(held_start, dict):
                current_start = held_start.get("value")
            if isinstance(held_end, dict):
                current_end = held_end.get("value")
        apply_patch(
            parking,
            "start",
            overlay_calendar_on_instant(current_start, session.locked_parking_start),
            source="current_turn",
            provenance="explicit",
        )
        apply_patch(
            parking,
            "end",
            overlay_calendar_on_instant(current_end, session.locked_parking_end),
            source="current_turn",
            provenance="explicit",
        )


def _overlay_parking_dates(
    session: AgentSession, change: BuyerRefinement, *, force: bool = False
) -> None:
    last = _last_user_text(session)
    if last and parse_parking_clock_window(last) and change.date_scope != "parking":
        return
    if not change.start_date or not change.end_date:
        return
    if change.date_scope == "stay" or change.hold_parking_dates:
        return
    if change.date_scope not in {"all", "parking"}:
        return
    if session.parking_dates_held:
        return
    last = _last_user_text(session)
    if (
        not force
        and change.date_scope == "all"
        and last
        and not is_explicit_date_mutation(last, change)
    ):
        return
    session.locked_parking_start = change.start_date
    session.locked_parking_end = change.end_date
    parking = session.domains.get("parking")
    if not isinstance(parking, dict):
        return
    fields = parking.get("fields") if isinstance(parking.get("fields"), dict) else {}
    current_start = None
    current_end = None
    if isinstance(fields, dict):
        held_start = fields.get("start")
        held_end = fields.get("end")
        if isinstance(held_start, dict):
            current_start = held_start.get("value")
        if isinstance(held_end, dict):
            current_end = held_end.get("value")
    apply_patch(
        parking,
        "start",
        overlay_calendar_on_instant(current_start, change.start_date),
        source="current_turn",
        provenance="explicit",
    )
    apply_patch(
        parking,
        "end",
        overlay_calendar_on_instant(current_end, change.end_date),
        source="current_turn",
        provenance="explicit",
    )
    mark_stale(parking, ["start", "end"])


def _apply_locked_facts(session: AgentSession) -> None:
    facts = session.projection.get("facts") if isinstance(session.projection, dict) else {}
    if isinstance(facts, dict):
        if session.answers.get("startDate"):
            facts["startDate"] = session.answers["startDate"]
            facts["hasExactDates"] = True
        if session.answers.get("endDate"):
            facts["endDate"] = session.answers["endDate"]
        if session.answers.get("startDate") and session.answers.get("endDate"):
            facts["dates"] = f"{session.answers['startDate']} to {session.answers['endDate']}"
        if not session.locked_destination:
            held = facts.get("destination")
            if isinstance(held, str) and held.strip() and _stay_explicit(session):
                session.locked_destination = held.strip()
        if session.locked_destination:
            facts["destination"] = session.locked_destination
        if session.locked_origin:
            facts["originCity"] = session.locked_origin
            origin_code = _unique_flight_code(
                session.locked_origin,
                str(session.answers.get("departureAirport") or ""),
            )
            if origin_code:
                facts["departureAirport"] = origin_code
                session.answers["departureAirport"] = origin_code
                _ensure_flight_domain(session)
                flight = session.domains["flight"]
                fields = flight.setdefault("fields", {})
                if not isinstance(fields, dict):
                    fields = {}
                    flight["fields"] = fields
                fields["origin"] = {
                    "value": origin_code,
                    "source": "current_turn",
                    "provenance": "explicit",
                }
                dest = _flight_field(session, "destination")
                if origin_code and dest:
                    session.flight_airports_resolved = True
    tasks = session.projection.get("tasks")
    if isinstance(tasks, list) and session.dropped_kinds:
        session.projection["tasks"] = [
            item
            for item in tasks
            if not (
                isinstance(item, dict)
                and str(item.get("kind") or "") in {"parking", *session.dropped_kinds}
            )
        ]
        if "parking" in session.dropped_kinds:
            session.domains.pop("parking", None)
    if "things to do" in session.extra_note.lower():
        experience = session.domains.get("experience")
        if not isinstance(experience, dict):
            session.domains["experience"] = empty_domain(
                "experience", provenance="explicit", accepted=True
            )
        else:
            experience["accepted"] = True
            experience["provenance"] = "explicit"
        if isinstance(tasks, list) and not any(
            isinstance(item, dict) and item.get("kind") == "experience" for item in tasks
        ):
            session.projection.setdefault("tasks", [])
            held = session.projection.get("tasks")
            if isinstance(held, list):
                held.append(
                    {
                        "id": "experience-added",
                        "kind": "experience",
                        "title": "Experience",
                        "provenance": "explicit",
                        "accepted": True,
                        "support": "sandbox_search",
                        "supportLabel": "Sandbox experience search",
                    }
                )


def _append_event(session: AgentSession, kind: str, message: str) -> None:
    session.events.append(
        {
            "sequence": len(session.events) + 1,
            "kind": kind,
            "message": message,
        }
    )


def _ingest_provider_events(session: AgentSession, raw: object) -> None:
    if not isinstance(raw, list):
        return
    for item in raw:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        message = item.get("message")
        if isinstance(kind, str) and isinstance(message, str):
            _append_event(session, kind, message)


def _apply_plan_result(session: AgentSession, result: Mapping[str, object]) -> None:
    projection = result.get("projection")
    if not isinstance(projection, dict):
        raise ApplicationError("model", "unavailable")
    session.projection = dict(projection)
    phase = projection.get("phase")
    if isinstance(phase, str) and phase in {"clarify", "forming", "ready"}:
        session.provider_phase = "forming" if phase == "ready" else phase
    plan_turn = result.get("planTurn")
    session.fallback = isinstance(plan_turn, dict) and plan_turn.get("fallback") is True
    _ingest_provider_events(session, result.get("events"))
    if session.fallback and not any(
        event.get("kind") == "FALLBACK_DETERMINISTIC" for event in session.events
    ):
        _append_event(session, "FALLBACK_DETERMINISTIC", FALLBACK_COPY)
    session.tool_trace.append({"kind": "plan"})
    synced = plan_turn if isinstance(plan_turn, dict) else None
    _sync_domains(session, source="current_turn", plan_turn=synced)
    _apply_locked_facts(session)
    _canonicalize_session_dates(session)
    if "parking" not in session.dropped_kinds:
        _ensure_parking_clocks_from_conversation(session, source="current_turn")
        parking = session.domains.get("parking")
        if isinstance(parking, dict):
            apply_defaults(parking)
            refresh_completeness(
                parking,
                str(session.pending_authorization["gate"])
                if session.pending_authorization
                else None,
            )
            _localize_parking_asks(session)
    _ensure_stay_destination(session)
    _accept_proposed_flight(session)
    _resolve_flight_prefs(session)
    _rewrite_agent_questions(session)
    message = ""
    if isinstance(plan_turn, dict):
        raw_message = plan_turn.get("buyerSafeMessage")
        if isinstance(raw_message, str):
            message = raw_message
    parking = session.domains.get("parking")
    offer_set = parking.get("offerSet") if isinstance(parking, dict) else None
    a2_complete = (
        isinstance(offer_set, dict)
        and offer_set.get("stale") is not True
        and isinstance(offer_set.get("snapshot"), dict)
    )
    session.buyer_safe_message = _compose_buyer_message(
        session, message, a2_complete=bool(a2_complete)
    )
    if session.last_refinement_note:
        session.buyer_safe_message = session.last_refinement_note
    _refresh_pending(session)
    _append_agent_turn(session, session.buyer_safe_message)


def _handoff_fields(raw: Mapping[str, object]) -> dict[str, object]:
    fields: dict[str, object] = {}
    for key in _HANDOFF_KEYS:
        if key in raw and key not in {"intentId", "buyerToken", "approvalId"}:
            fields[key] = raw[key]
    return fields


def _append_user_turn(session: AgentSession, text: str) -> None:
    cleaned = text.strip()
    if not cleaned:
        return
    session.transcript.append({"turnId": mint_opaque("tn_"), "role": "user", "text": cleaned})


def _append_agent_turn(session: AgentSession, text: str) -> None:
    cleaned = text.strip()
    if not cleaned:
        return
    if (
        session.transcript
        and session.transcript[-1].get("role") == "agent"
        and session.transcript[-1].get("text") == cleaned
    ):
        return
    session.transcript.append({"turnId": mint_opaque("tn_"), "role": "agent", "text": cleaned})


def _conversation(session: AgentSession) -> str:
    parts = [session.objective.strip(), session.extra_note.strip()]
    for item in session.transcript:
        if item.get("role") == "user":
            parts.append(str(item.get("text") or ""))
    return " ".join(part for part in parts if part)


def _last_user_text(session: AgentSession) -> str:
    for item in reversed(session.transcript):
        if item.get("role") == "user":
            return str(item.get("text") or "")
    return session.objective.strip()


def _trusted_snapshot(session: AgentSession) -> dict[str, object]:
    out: dict[str, object] = {}
    for kind, domain in session.domains.items():
        fields_raw = domain.get("fields") if isinstance(domain.get("fields"), dict) else {}
        fields: dict[str, object] = {}
        if isinstance(fields_raw, dict):
            for field_id, held in fields_raw.items():
                if isinstance(held, dict):
                    fields[str(field_id)] = {
                        "value": held.get("value"),
                        "provenance": held.get("provenance"),
                        "source": held.get("source"),
                    }
        out[kind] = {
            "accepted": domain.get("accepted"),
            "provenance": domain.get("provenance"),
            "fields": fields,
            "missing": domain.get("missing"),
            "ask": domain.get("ask"),
        }
    last_agent = ""
    for item in reversed(session.transcript):
        if item.get("role") == "agent":
            last_agent = str(item.get("text") or "")
            break
    if last_agent:
        out["lastAgentMessage"] = last_agent
    turns: list[dict[str, object]] = []
    for item in session.transcript[-20:]:
        role = str(item.get("role") or "")
        text = str(item.get("text") or "").strip()
        if role and text:
            turns.append({"role": role, "text": text})
    if turns:
        out["recentTurns"] = turns
    authorized = [
        kind
        for kind, domain in session.domains.items()
        if isinstance(domain, dict) and domain.get("completeness") == "authorized"
    ]
    stay_start, stay_end = _stay_window(session)
    flight_start = _flight_field(session, "date")
    flight_end = _flight_field(session, "dateEnd") or session.flight_draft_end
    out["sessionFacts"] = {
        "sandboxSearchOnly": True,
        "authorizedDomains": authorized,
        "hasFlightSearch": session.flight_search is not None,
        "hasStaySearch": session.stay_search is not None,
        "stayDates": {"start": stay_start, "end": stay_end},
        "flightDates": {"start": flight_start, "end": flight_end},
        "tripDates": {
            "start": str(session.answers.get("startDate") or stay_start),
            "end": str(session.answers.get("endDate") or stay_end),
        },
    }
    facts = session.projection.get("facts") if isinstance(session.projection, dict) else {}
    if isinstance(facts, dict):
        origin = str(facts.get("originCity") or "").strip()
        dest = str(facts.get("destination") or "").strip()
        if origin or dest:
            out["trip"] = {
                "originCity": origin,
                "destination": dest,
                "startDate": str(facts.get("startDate") or session.answers.get("startDate") or ""),
                "endDate": str(facts.get("endDate") or session.answers.get("endDate") or ""),
            }
    return out


def _sync_domains(
    session: AgentSession,
    *,
    source: str,
    plan_turn: Mapping[str, object] | None = None,
) -> None:
    tasks = session.projection.get("tasks")
    if not isinstance(tasks, list):
        tasks = []
    for item in tasks:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        if kind not in {"parking", "rental", "hotel", "experience", "flight"}:
            continue
        domain_key = "stay" if kind == "hotel" else str(kind)
        if domain_key in session.dropped_kinds or str(kind) in session.dropped_kinds:
            continue
        provenance = str(item.get("provenance") or "proposed")
        accepted = item.get("accepted") is True or provenance == "explicit"
        if kind in {"parking", "hotel", "experience"} and not accepted:
            continue
        domain_key = "stay" if kind == "hotel" else str(kind)
        domain_kind = "hotel" if kind == "hotel" else str(kind)
        current = session.domains.get(domain_key)
        if current is None:
            session.domains[domain_key] = empty_domain(
                domain_kind,  # type: ignore[arg-type]
                provenance=provenance,
                accepted=accepted,
            )
        else:
            current["provenance"] = provenance
            if accepted:
                current["accepted"] = True
    _apply_model_requirement_patches(session, plan_turn, source=source)
    if "parking" not in session.dropped_kinds:
        _seed_parking_from_facts(session, source=source)
    _apply_extracted_patches(session, source=source)
    _reapply_last_date_refinement(session)
    _seed_flight_from_facts(session, source=source)
    _ensure_parking_clocks_from_conversation(session, source=source)
    parking = session.domains.get("parking")
    if isinstance(parking, dict):
        apply_defaults(parking)
        refresh_completeness(
            parking,
            str(session.pending_authorization["gate"]) if session.pending_authorization else None,
        )
    rental = session.domains.get("rental")
    if isinstance(rental, dict):
        refresh_completeness(rental, None)
    _localize_parking_asks(session)


def _localize_parking_asks(session: AgentSession) -> None:
    parking = session.domains.get("parking")
    facts = session.projection.get("facts")
    dest = facts.get("destination") if isinstance(facts, dict) else ""
    if not isinstance(parking, dict):
        return
    asks = parking.get("ask")
    if not isinstance(asks, list):
        return
    prompt = parking_airport_ask(str(dest or ""))
    for item in asks:
        if isinstance(item, dict) and item.get("id") == "airportCode":
            item["ask"] = prompt


def _parking_led(session: AgentSession) -> bool:
    parking = session.domains.get("parking")
    return isinstance(parking, dict) and (
        parking.get("accepted") is True or str(parking.get("provenance") or "") == "explicit"
    )


def _stay_explicit(session: AgentSession) -> bool:
    stay = session.domains.get("stay")
    if isinstance(stay, dict) and (
        stay.get("accepted") is True or str(stay.get("provenance") or "") == "explicit"
    ):
        return True
    tasks = session.projection.get("tasks")
    if not isinstance(tasks, list):
        return False
    for item in tasks:
        if not isinstance(item, dict):
            continue
        if item.get("kind") != "hotel":
            continue
        if item.get("accepted") is True or str(item.get("provenance") or "") == "explicit":
            return True
    return False


def _non_parking_booking_request(session: AgentSession) -> bool:
    if _parking_led(session) or _stay_explicit(session):
        return False
    for kind in ("rental", "ents"):
        domain = session.domains.get(kind)
        if isinstance(domain, dict) and (
            domain.get("accepted") is True or str(domain.get("provenance") or "") == "explicit"
        ):
            return True
    tasks = session.projection.get("tasks")
    if not isinstance(tasks, list):
        return False
    for item in tasks:
        if not isinstance(item, dict):
            continue
        if item.get("kind") not in {"rental", "ents"}:
            continue
        if item.get("accepted") is True or str(item.get("provenance") or "") == "explicit":
            return True
    return False


def _next_catalog_ask(session: AgentSession) -> str:
    parking = session.domains.get("parking")
    if isinstance(parking, dict):
        combined = join_catalog_asks(parking.get("ask"))
        if combined:
            return combined
    rental = session.domains.get("rental")
    if isinstance(rental, dict):
        return join_catalog_asks(rental.get("ask"))
    return ""


def _rewrite_agent_questions(session: AgentSession) -> None:
    if not _parking_led(session):
        return
    projection = session.projection
    if isinstance(projection, dict):
        projection["questions"] = []
        if projection.get("phase") == "clarify":
            projection["phase"] = "forming"
    if session.provider_phase == "clarify":
        session.provider_phase = "forming"


_TRIP_FUNNEL_RE = re.compile(
    r"\b(departing from|will you need a car|exact dates|when are you travelling)\b",
    re.I,
)
_DATE_ASK_RE = re.compile(r"\b(exact dates|when are you travelling)\b", re.I)
_PARKING_VEHICLE_ASK_RE = re.compile(r"\bvehicle class\b", re.I)


def _compose_buyer_message(session: AgentSession, model_message: str, *, a2_complete: bool) -> str:
    last = _last_user_text(session)
    if re.search(r"\b(pay for|purchase|ticket)\s+(?:a |the )?flights?\b", last, re.I):
        return sanitize_buyer_message(FLIGHT_UNSUPPORTED_COPY, a2_complete=a2_complete)
    if _non_parking_booking_request(session):
        rental = session.domains.get("rental")
        rental_explicit = isinstance(rental, dict) and (
            rental.get("accepted") is True or str(rental.get("provenance") or "") == "explicit"
        )
        if rental_explicit:
            return RENTAL_NO_ADAPTER_COPY
        return COMPETITION_PARKING_ONLY_COPY
    next_ask = _next_catalog_ask(session)
    cleaned = sanitize_buyer_message(model_message, a2_complete=a2_complete)
    parking = session.domains.get("parking")
    fields = parking.get("fields") if isinstance(parking, dict) else {}
    dates_known = (
        isinstance(parking, dict)
        and not _empty_field(fields, "start")
        and not _empty_field(fields, "end")
    )
    parking_led = _parking_led(session)
    ask_ids: set[str] = set()
    asks = parking.get("ask") if isinstance(parking, dict) else None
    if isinstance(asks, list):
        for item in asks:
            if isinstance(item, dict) and item.get("id"):
                ask_ids.add(str(item["id"]))
    if parking_led and next_ask:
        stale = _TRIP_FUNNEL_RE.search(cleaned) is not None
        if dates_known and _DATE_ASK_RE.search(cleaned):
            stale = True
        if _PARKING_VEHICLE_ASK_RE.search(cleaned) and "vehicleClass" not in ask_ids:
            stale = True
        if stale or not cleaned.strip() or next_ask.lower() not in cleaned.lower():
            return sanitize_buyer_message(next_ask, a2_complete=a2_complete)
    if (
        parking_led
        and not next_ask
        and _PARKING_VEHICLE_ASK_RE.search(cleaned)
        and "vehicleClass" not in ask_ids
    ):
        return ""
    return cleaned


def _apply_model_requirement_patches(
    session: AgentSession, plan_turn: Mapping[str, object] | None, *, source: str
) -> None:
    if not isinstance(plan_turn, Mapping):
        return
    raw = plan_turn.get("requirementPatches")
    if not isinstance(raw, list) or not raw:
        return
    patches = [item for item in raw if isinstance(item, Mapping)]
    change = _session_refinement(session)
    if change is not None and change.date_scope in {"stay", "flight"}:
        patches = [
            item
            for item in patches
            if not (
                str(item.get("kind") or "") == "parking"
                and str(item.get("fieldId") or "") in {"start", "end", "startTime", "endTime"}
            )
        ]
    if change is not None and change.flight_origin:
        patches = [
            item
            for item in patches
            if not (
                str(item.get("kind") or "") == "parking"
                and str(item.get("fieldId") or "") == "airportCode"
            )
        ]
    accepted, rejected = apply_model_patches(
        session.domains,
        patches,
        conversation=_conversation(session),
        last_user_message=_last_user_text(session),
        source=source,  # type: ignore[arg-type]
    )
    accepted_ids = [f"{item.get('kind')}.{item.get('fieldId')}" for item in accepted]
    rejected_ids = [
        f"{item.get('kind')}.{item.get('fieldId')}:{item.get('reason')}:{item.get('value')!r}"[:96]
        for item in rejected
    ]
    sys.stderr.write(
        "itaa_agent_patches "
        f"accepted={accepted_ids} rejected={rejected_ids} fallback={session.fallback}\n"
    )


def _apply_extracted_patches(session: AgentSession, *, source: str) -> None:
    conversation = _conversation(session)
    last = _last_user_text(session) or ""
    last_change = _session_refinement(session)
    skip_parking_dates = bool(
        last
        and last_change is not None
        and (
            last_change.date_scope in {"stay", "flight"}
            or last_change.hold_parking_dates
            or (
                is_explicit_date_mutation(last, last_change)
                and last_change.date_scope == "all"
                and parse_parking_clock_window(last) is None
            )
        )
    )
    patches = extract_conversation_patches(conversation, source=source)  # type: ignore[arg-type]
    if last and last.strip() and last.strip() != conversation.strip():
        patches.extend(
            extract_conversation_patches(
                last,
                source=source,  # type: ignore[arg-type]
                calendar_context=conversation,
            )
        )
    parking_changed: list[str] = []
    for patch in patches:
        kind = str(patch.get("kind") or "")
        if kind == "parking" and "parking" in session.dropped_kinds:
            continue
        domain_key = "stay" if kind == "hotel" else kind
        domain = session.domains.get(domain_key)
        if not isinstance(domain, dict):
            continue
        field_id = str(patch.get("fieldId") or "")
        if (
            kind == "parking"
            and last_change is not None
            and last_change.flight_origin
            and field_id == "airportCode"
        ):
            continue
        if (
            kind == "parking"
            and field_id == "airportCode"
            and (_ALL_AIRPORTS_RE.search(last) or _ALL_AIRPORTS_REPLY_RE.fullmatch(last.strip()))
        ):
            continue
        if (
            kind == "parking"
            and (
                session.parking_dates_held
                or skip_parking_dates
                or (last_change is not None and last_change.date_scope == "stay")
            )
            and field_id in {"start", "end"}
        ):
            continue
        if field_id in {"startTime", "endTime"}:
            target = "start" if field_id == "startTime" else "end"
            fields = domain.get("fields")
            current = None
            if isinstance(fields, dict):
                held = fields.get(target)
                if isinstance(held, dict):
                    current = held.get("value")
            inst = overlay_time_on_instant(current, str(patch.get("value") or ""))
            if (
                inst
                and apply_patch(
                    domain,
                    target,
                    inst,
                    source=source,  # type: ignore[arg-type]
                    provenance="explicit",
                )
                and kind == "parking"
            ):
                parking_changed.append(target)
            continue
        if field_id in {"start", "end"}:
            fields = domain.get("fields")
            current = None
            if isinstance(fields, dict):
                held = fields.get(field_id)
                if isinstance(held, dict):
                    current = held.get("value")
            if date_mutation_without_calendar(current, patch.get("value"), conversation):
                continue
            value = patch.get("value")
            kept = keep_existing_clock(current, value)
            if kept is not None:
                value = kept
            if (
                apply_patch(
                    domain,
                    field_id,
                    value,
                    source=source,  # type: ignore[arg-type]
                    provenance="explicit",
                )
                and kind == "parking"
            ):
                parking_changed.append(field_id)
            continue
        if (
            apply_patch(
                domain,
                field_id,
                patch.get("value"),
                source=source,  # type: ignore[arg-type]
                provenance="explicit",
            )
            and kind == "parking"
        ):
            parking_changed.append(field_id)
    parking = session.domains.get("parking")
    if isinstance(parking, dict) and parking_changed:
        mark_stale(parking, parking_changed)


def _seed_parking_from_facts(session: AgentSession, *, source: str) -> None:
    parking = session.domains.get("parking")
    facts = session.projection.get("facts")
    if not isinstance(parking, dict) or not isinstance(facts, dict):
        return
    fields = parking.get("fields") if isinstance(parking.get("fields"), dict) else {}
    last = _last_user_text(session) or ""
    window = parse_parking_clock_window(last)
    if window is None and _empty_field(fields, "start") and _empty_field(fields, "end"):
        window = parse_parking_clock_window(_conversation(session))
    if window:
        apply_patch(
            parking,
            "start",
            window[0],
            source=source,  # type: ignore[arg-type]
            provenance="explicit",
        )
        apply_patch(
            parking,
            "end",
            window[1],
            source=source,  # type: ignore[arg-type]
            provenance="explicit",
        )
        session.locked_parking_start = window[0][:10]
        session.locked_parking_end = window[1][:10]
    airport = facts.get("parkingAirport")
    if isinstance(airport, str) and airport and _empty_field(fields, "airportCode"):
        apply_patch(
            parking,
            "airportCode",
            airport,
            source=source,  # type: ignore[arg-type]
            provenance="explicit",
        )
    destination = str(facts.get("destination") or "")
    solo = single_city_airport(destination)
    if solo and _empty_field(fields, "airportCode"):
        apply_patch(
            parking,
            "airportCode",
            solo,
            source=source,  # type: ignore[arg-type]
            provenance="explicit",
        )
    start_date = facts.get("startDate") if isinstance(facts.get("startDate"), str) else ""
    end_date = facts.get("endDate") if isinstance(facts.get("endDate"), str) else ""
    if window is None and start_date and _empty_field(fields, "start"):
        apply_patch(
            parking,
            "start",
            start_date,
            source=source,  # type: ignore[arg-type]
            provenance="explicit",
        )
    if window is None and end_date and _empty_field(fields, "end"):
        apply_patch(
            parking,
            "end",
            end_date,
            source=source,  # type: ignore[arg-type]
            provenance="explicit",
        )
    _ensure_parking_clocks_from_conversation(session, source=source)


def _ensure_parking_clocks_from_conversation(session: AgentSession, *, source: str) -> None:
    parking = session.domains.get("parking")
    if not isinstance(parking, dict):
        return
    fields = parking.get("fields") if isinstance(parking.get("fields"), dict) else {}
    if not isinstance(fields, dict):
        return
    blob = f"{_conversation(session)} {_last_user_text(session)}"
    match = CLOCK_SPAN_RE.search(blob)
    if match is None:
        return
    facts = session.projection.get("facts") if isinstance(session.projection, dict) else {}
    fact_start = str(facts.get("startDate") or "") if isinstance(facts, dict) else ""
    fact_end = str(facts.get("endDate") or "") if isinstance(facts, dict) else ""
    start_held = fields.get("start")
    end_held = fields.get("end")
    start_val = start_held.get("value") if isinstance(start_held, dict) else None
    end_val = end_held.get("value") if isinstance(end_held, dict) else None
    if _placeholder_clock(start_val):
        current = start_val if isinstance(start_val, str) and len(start_val) >= 10 else fact_start
        inst = overlay_time_on_instant(current, match.group(1))
        if inst:
            apply_patch(parking, "start", inst, source=source, provenance="explicit")  # type: ignore[arg-type]
    if _placeholder_clock(end_val):
        current = end_val if isinstance(end_val, str) and len(end_val) >= 10 else fact_end
        inst = overlay_time_on_instant(current, match.group(2))
        if inst:
            apply_patch(parking, "end", inst, source=source, provenance="explicit")  # type: ignore[arg-type]


def _placeholder_clock(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return True
    if "T" not in value:
        return True
    return bool(re.search(r"T(?:00:00|12:00)(?::00)?(?:Z)?$", value))


def _empty_field(fields: object, field_id: str) -> bool:
    if not isinstance(fields, dict):
        return True
    held = fields.get(field_id)
    if not isinstance(held, dict):
        return True
    return held.get("value") in (None, "")


def _apply_direct_patches(session: AgentSession, patches: Sequence[Mapping[str, object]]) -> None:
    changed: list[str] = []
    for patch in patches:
        kind = str(patch.get("domain") or patch.get("kind") or "")
        domain = session.domains.get(kind)
        if not isinstance(domain, dict):
            raise ApplicationError("domain", "unknown_resource")
        field_id = str(patch.get("fieldId") or "")
        if apply_patch(
            domain,
            field_id,
            patch.get("value"),
            source="direct_edit",
            provenance="explicit",
        ):
            changed.append(field_id)
    parking = session.domains.get("parking")
    if isinstance(parking, dict) and changed:
        mark_stale(parking, changed)
        apply_defaults(parking)
        refresh_completeness(parking, None)
        _refresh_pending(session)


def _refresh_pending(session: AgentSession) -> None:
    parking = session.domains.get("parking")
    if not isinstance(parking, dict) or parking.get("accepted") is not True:
        session.pending_authorization = None
        return
    apply_defaults(parking)
    offer = parking.get("offerSet") if isinstance(parking.get("offerSet"), dict) else {}
    stale = bool(isinstance(offer, dict) and offer.get("stale"))
    snapshot = offer.get("snapshot") if isinstance(offer, dict) else None
    refresh_completeness(parking, None)
    _localize_parking_asks(session)
    missing = parking.get("missing") if isinstance(parking.get("missing"), list) else []
    if missing:
        prompt = _next_catalog_ask(session) or "Which parking details are still missing?"
        session.pending_authorization = None
        if not session.search_execution:
            session.buyer_safe_message = sanitize_buyer_message(prompt, a2_complete=False)
        return
    if isinstance(snapshot, dict) and snapshot.get("transaction"):
        parking["completeness"] = "authorized"
        session.pending_authorization = None
        return
    if isinstance(snapshot, dict) and snapshot.get("acceptance") and not stale:
        parking["completeness"] = "accepted"
        offers = snapshot.get("offers")
        if isinstance(offers, list):
            rec = snapshot.get("recommendedOfferId")
            for item in offers:
                if isinstance(item, dict) and item.get("offerId") == rec:
                    amount, currency = _offer_amount(item)
                    session.pending_authorization = {
                        "gate": "A4",
                        "domain": "parking",
                        "prompt": (
                            f"Authorize a simulated reservation of {currency} "
                            f"{(int(amount) / 100):.2f}?"
                            if isinstance(amount, int)
                            else "Authorize a simulated reservation?"
                        ),
                        "resourceId": snapshot.get("intentId"),
                    }
                    parking["completeness"] = "awaiting_grant"
                    return
        session.pending_authorization = {
            "gate": "A4",
            "domain": "parking",
            "prompt": "Authorize a simulated reservation?",
            "resourceId": snapshot.get("intentId"),
        }
        parking["completeness"] = "awaiting_grant"
        return
    if isinstance(snapshot, dict) and snapshot.get("offers") and not stale:
        rec = snapshot.get("recommendedOfferId")
        prompt = _offer_accept_prompt(snapshot)
        session.pending_authorization = {
            "gate": "A3",
            "domain": "parking",
            "prompt": prompt,
            "resourceId": snapshot.get("intentId"),
            "offerId": rec,
        }
        parking["completeness"] = "offers"
        return
    session.pending_authorization = None
    parking["completeness"] = "ready"


def _offer_accept_prompt(snapshot: Mapping[str, object]) -> str:
    offers = snapshot.get("offers")
    rec = snapshot.get("recommendedOfferId")
    parts = ["Simulated parking offers from 3 isolated suppliers."]
    if isinstance(offers, list):
        for item in offers:
            if not isinstance(item, dict):
                continue
            rank = item.get("rank")
            amount, currency = _offer_amount(item)
            recommended = item.get("offerId") == rec or item.get("recommended") is True
            marker = " recommended" if recommended else ""
            if isinstance(amount, int):
                parts.append(f"Rank {rank}{marker}: {currency} {(amount / 100):.2f}.")
            else:
                parts.append(f"Rank {rank}{marker}.")
    parts.append("Select a simulated offer on the parking card. Selection is not a booking.")
    return " ".join(parts)


def _offer_amount(item: Mapping[str, object]) -> tuple[object, object]:
    price = item.get("price") if isinstance(item.get("price"), dict) else {}
    total = item.get("totalMinor")
    if total is None and isinstance(price, dict):
        total = price.get("totalMinor")
    currency = item.get("currency")
    if not currency and isinstance(price, dict):
        currency = price.get("currency")
    return total, currency or "USD"


def _shared_booking_context(session: AgentSession) -> dict[str, object]:
    facts = session.projection.get("facts") if isinstance(session.projection, dict) else {}
    if not isinstance(facts, dict):
        facts = {}
    items: list[dict[str, object]] = []
    mapping = (
        ("originCity", "origin"),
        ("destination", "destination"),
        ("dates", "dates"),
        ("startDate", "startDate"),
        ("endDate", "endDate"),
    )
    for key, label in mapping:
        value = facts.get(key)
        if isinstance(value, str) and value.strip():
            items.append(
                {
                    "id": key,
                    "label": label,
                    "value": value.strip(),
                    "source": "buyer",
                    "provenance": "explicit",
                }
            )
    if facts.get("rentalStated") is True:
        items.append(
            {
                "id": "travellersPreference",
                "label": "preference",
                "value": "rental car requested",
                "source": "buyer",
                "provenance": "explicit",
            }
        )
    return {
        "facts": items,
        "note": (
            "Shared context never travels as one payload. Each capability sends only its envelope."
        ),
    }


def _public_projection(session: AgentSession) -> dict[str, object]:
    projection = deepcopy(session.projection)
    if session.confirmed:
        projection["phase"] = "ready"
        projection["questions"] = []
        projection["summary"] = CONFIRMED_COPY
    return projection


def _public_session(session: AgentSession) -> dict[str, object]:
    projection = _public_projection(session)
    questions = projection.get("questions")
    pending = session.pending_authorization
    return {
        "sessionId": session.session_id,
        "projection": projection,
        "questions": questions if isinstance(questions, list) else [],
        "toolTrace": list(session.tool_trace),
        "pendingAuthorizations": list(session.pending_authorizations),
        "pendingAuthorization": None if pending is None else dict(pending),
        "parkingHandoff": (
            None if session.parking_handoff is None else dict(session.parking_handoff)
        ),
        "confirmed": session.confirmed,
        "fallback": session.fallback,
        "correlationId": session.correlation_id,
        "transcript": list(session.transcript),
        "domains": {kind: public_domain(item) for kind, item in session.domains.items()},
        "buyerSafeMessage": session.buyer_safe_message,
        "staySearch": None if session.stay_search is None else dict(session.stay_search),
        "experienceSearch": (
            None if session.experience_search is None else dict(session.experience_search)
        ),
        "flightSearch": None if session.flight_search is None else dict(session.flight_search),
        "pendingSearchAuthorization": public_pending(session.pending_search_authorization),
        "searchExecution": list(session.search_execution),
        "pendingDateCascade": (
            None if session.pending_date_cascade is None else dict(session.pending_date_cascade)
        ),
        "lastRevisedKind": session.last_revised_kind or None,
        "stayDraft": {
            "checkIn": session.stay_draft_start or None,
            "checkOut": session.stay_draft_end or None,
        },
        "sharedBookingContext": _shared_booking_context(session),
        "workspace": {
            "persistence": "process-local",
            "note": (
                "Running and Pending are this browser session. "
                "API restart drops agent sessions; resume is not durable."
            ),
        },
    }


def _has_projected_plan(session: AgentSession) -> bool:
    facts = session.projection.get("facts") if isinstance(session.projection, dict) else None
    return isinstance(facts, dict) and bool(
        facts.get("destination") or facts.get("originCity") or facts.get("startDate")
    )


def _is_airport_choice_reply(text: str) -> bool:
    cleaned = text.strip()
    if not cleaned or re.search(r"\bparking\b", cleaned, re.I):
        return False
    if _ALL_AIRPORTS_RE.search(cleaned) or _ALL_AIRPORTS_REPLY_RE.fullmatch(cleaned):
        return True
    if len(cleaned) > 40:
        return False
    if _parse_flight_airport_pair(cleaned) != ("", ""):
        return True
    return bool(resolve_airport_reply(cleaned))


def _continue_after_plan(
    request: Request, session: AgentSession, result: Mapping[str, object] | None
) -> None:
    if result is not None:
        _apply_plan_result(session, result)
    _apply_airport_reply(session)
    plan_turn = result.get("planTurn") if isinstance(result, Mapping) else None
    _apply_flight_airport_reply(
        session, plan_turn=plan_turn if isinstance(plan_turn, Mapping) else None
    )
    _reconcile_search_authorization(request, session)


def _plan(request: Request, session: AgentSession) -> None:
    _apply_conversation_refinements(session)
    provider = _provider(request)
    payload: dict[str, object] = {
        "objective": _provider_objective(session),
        "answers": dict(session.answers),
        "correlationId": session.correlation_id,
        "lastUserMessage": _last_user_text(session),
        "trustedDomains": _trusted_snapshot(session),
    }
    try:
        result = provider.plan_turn(payload)
        _continue_after_plan(request, session, result)
        return
    except ApplicationError as exc:
        if _has_projected_plan(session) and _is_airport_choice_reply(_last_user_text(session)):
            _continue_after_plan(request, session, None)
            return
        _append_event(session, "FAILED_CLOSED", FAILED_COPY)
        raise exc
    except Exception:
        if _has_projected_plan(session) and _is_airport_choice_reply(_last_user_text(session)):
            _continue_after_plan(request, session, None)
            return
        _append_event(session, "FAILED_CLOSED", FAILED_COPY)
        raise ApplicationError("model", "unavailable") from None


def _execute(
    request: Request, session: AgentSession, tool: str, payload: Mapping[str, object]
) -> dict[str, object]:
    if tool in _MUTATING_TOOLS and not session.confirmed:
        raise ApplicationError("plan", "illegal_state")
    provider = _provider(request)
    body: dict[str, object] = {
        "tool": tool,
        "payload": dict(payload),
        "correlationId": session.correlation_id,
    }
    try:
        result = provider.execute_turn(body)
    except ApplicationError as exc:
        if exc.field == "approvalId":
            session.pending_authorizations.append(
                {"tool": tool, "field": exc.field, "code": exc.code}
            )
        _append_event(session, "FAILED_CLOSED", FAILED_COPY)
        raise exc
    except Exception:
        _append_event(session, "FAILED_CLOSED", FAILED_COPY)
        raise ApplicationError("model", "unavailable") from None
    session.tool_trace.append({"kind": "execute", "tool": tool})
    inner = result.get("result") if isinstance(result, dict) else None
    if not isinstance(inner, dict):
        raise ApplicationError("model", "unavailable")
    return dict(inner)


def _dispatch_capability_searches(
    request: Request,
    session: AgentSession,
    capabilities: Sequence[str] | None = None,
) -> None:
    """Dispatch only buyer-authorized search capabilities.

    Destination plus dates never activates stay.search or experience.search. Unconfigured
    capabilities (rental.search) stay silent — no simulated substitute. Parking search
    uses the simulated supplier path after search authorization, not A3–A4.
    """

    allowed = None if capabilities is None else [str(item) for item in capabilities]
    session.search_execution = []
    if allowed:
        for capability in allowed:
            session.search_execution.append(
                {
                    "capability": capability,
                    "authorized": True,
                    "dispatched": False,
                    "outcome": "failed",
                }
            )
    tasks, facts = snapshots_from_projection(session.projection)
    established = set(established_capabilities(tasks, facts))
    if allowed is None or SEARCH_STAY in allowed:
        if Capability.STAY_SEARCH in established:
            before = session.stay_search
            stay_start, stay_end = _stay_window(session, facts)
            _search_stay_offers(
                request,
                session,
                facts.destination,
                stay_start,
                stay_end,
                facts.origin_city,
            )
            _record_search_outcome(session, SEARCH_STAY, dispatched=True)
            del before
        elif allowed is not None:
            _record_search_outcome(session, SEARCH_STAY, dispatched=False, outcome="failed")
    if allowed is None or SEARCH_EXPERIENCE in allowed:
        if Capability.EXPERIENCE_SEARCH in established:
            prefs = _experience_preferences(session)
            _search_experience_offers(request, session, facts.destination, prefs)
            _record_search_outcome(session, SEARCH_EXPERIENCE, dispatched=True)
        elif allowed is not None:
            _record_search_outcome(session, SEARCH_EXPERIENCE, dispatched=False, outcome="failed")
    if allowed is None or SEARCH_FLIGHT in allowed:
        if _flight_search_ready(session) and "flight" in _explicit_search_kinds(session):
            _search_flight_offers(request, session)
            _record_search_outcome(session, SEARCH_FLIGHT, dispatched=True)
        elif allowed is not None:
            _record_search_outcome(session, SEARCH_FLIGHT, dispatched=False, outcome="failed")
    if allowed is None or SEARCH_PARKING in allowed:
        if _parking_search_ready(session):
            try:
                _dispatch_parking_search(request, session)
                _record_search_outcome(session, SEARCH_PARKING, dispatched=True)
            except ApplicationError:
                _record_search_outcome(session, SEARCH_PARKING, dispatched=True, outcome="failed")
        elif allowed is not None:
            _record_search_outcome(session, SEARCH_PARKING, dispatched=False, outcome="failed")


def _record_search_outcome(
    session: AgentSession,
    capability: str,
    *,
    dispatched: bool,
    outcome: str | None = None,
) -> None:
    inferred = outcome or _capability_outcome(session, capability)
    for item in session.search_execution:
        if item.get("capability") == capability:
            item["dispatched"] = dispatched
            item["outcome"] = inferred
            return
    session.search_execution.append(
        {
            "capability": capability,
            "authorized": True,
            "dispatched": dispatched,
            "outcome": inferred,
        }
    )


def _capability_outcome(session: AgentSession, capability: str) -> str:
    if capability == SEARCH_STAY:
        current = session.stay_search if isinstance(session.stay_search, dict) else {}
        offers = current.get("offers") if isinstance(current, dict) else None
        status = str(current.get("status") or "") if isinstance(current, dict) else ""
        if status == "ok" and isinstance(offers, list) and offers:
            return "succeeded"
        if status == "ok":
            return "empty"
        return "failed"
    if capability == SEARCH_FLIGHT:
        current = session.flight_search if isinstance(session.flight_search, dict) else {}
        offers = current.get("offers") if isinstance(current, dict) else None
        status = str(current.get("status") or "") if isinstance(current, dict) else ""
        if isinstance(offers, list) and offers:
            return "succeeded"
        if status == "ok":
            return "empty"
        return "failed"
    if capability == SEARCH_EXPERIENCE:
        current = session.experience_search if isinstance(session.experience_search, dict) else {}
        offers = current.get("offers") if isinstance(current, dict) else None
        if isinstance(offers, list) and offers:
            return "succeeded"
        return "empty"
    if capability == SEARCH_PARKING:
        parking = session.domains.get("parking")
        offer = parking.get("offerSet") if isinstance(parking, dict) else None
        snapshot = offer.get("snapshot") if isinstance(offer, dict) else None
        offers = snapshot.get("offers") if isinstance(snapshot, dict) else None
        if isinstance(offers, list) and offers:
            return "succeeded"
        return "failed"
    return "failed"


def _parking_search_ready(session: AgentSession) -> bool:
    parking = session.domains.get("parking")
    if not isinstance(parking, dict) or parking.get("accepted") is not True:
        return False
    missing = parking.get("missing") if isinstance(parking.get("missing"), list) else []
    if missing:
        return False
    offer_held = parking.get("offerSet")
    offer = offer_held if isinstance(offer_held, dict) else {}
    snapshot = offer.get("snapshot")
    return not (
        isinstance(snapshot, dict) and snapshot.get("offers") and offer.get("stale") is not True
    )


def _parking_fingerprint(session: AgentSession) -> str:
    parking = session.domains.get("parking")
    if not isinstance(parking, dict):
        return ""
    fields = parking.get("fields") if isinstance(parking.get("fields"), dict) else {}
    parts: list[str] = []
    for field_id in ("airportCode", "start", "end", "vehicleClass", "covered"):
        held = fields.get(field_id) if isinstance(fields, dict) else None
        value = held.get("value") if isinstance(held, dict) else ""
        parts.append(str(value or ""))
    return "|".join(parts)


def _search_place(session: AgentSession) -> str:
    parking = session.domains.get("parking")
    fields = parking.get("fields") if isinstance(parking, dict) else {}
    airport = ""
    if isinstance(fields, dict):
        held = fields.get("airportCode")
        if isinstance(held, dict):
            airport = str(held.get("value") or "")
    facts = session.projection.get("facts") if isinstance(session.projection, dict) else {}
    dest = str(facts.get("destination") or "") if isinstance(facts, dict) else ""
    return dest or airport or "those dates"


def _ensure_stay_destination(session: AgentSession) -> None:
    facts = session.projection.get("facts") if isinstance(session.projection, dict) else {}
    if not isinstance(facts, dict) or str(facts.get("destination") or "").strip():
        return
    if not _stay_explicit(session):
        return
    airport = (
        str(facts.get("destinationAirport") or facts.get("parkingAirport") or "").strip().upper()
    )
    if not airport:
        parking = session.domains.get("parking")
        fields = parking.get("fields") if isinstance(parking, dict) else {}
        if isinstance(fields, dict):
            held = fields.get("airportCode")
            if isinstance(held, dict):
                airport = str(held.get("value") or "").strip().upper()
    place = IATA_STAY_PLACE.get(airport)
    if not place:
        return
    facts["destination"] = place
    if not str(facts.get("destinationAirport") or "").strip():
        facts["destinationAirport"] = airport


def _rental_explicit(session: AgentSession) -> bool:
    rental = session.domains.get("rental")
    if isinstance(rental, dict) and (
        rental.get("accepted") is True or str(rental.get("provenance") or "") == "explicit"
    ):
        return True
    tasks = session.projection.get("tasks")
    if not isinstance(tasks, list):
        return False
    for item in tasks:
        if not isinstance(item, dict) or item.get("kind") != "rental":
            continue
        if item.get("accepted") is True or str(item.get("provenance") or "") == "explicit":
            return True
    return False


def _current_search_fingerprints(session: AgentSession) -> dict[str, str]:
    tasks, facts = snapshots_from_projection(session.projection)
    prints: dict[str, str] = {}
    stay_start, stay_end = _stay_window(session, facts)
    if facts.destination and stay_start and stay_end:
        stay_parts = [facts.destination, stay_start, stay_end]
        if session.stay_max_amount_minor is not None:
            stay_parts.append(str(session.stay_max_amount_minor))
        prints[SEARCH_STAY] = "|".join(stay_parts)
    if _parking_fingerprint(session):
        prints[SEARCH_PARKING] = _parking_fingerprint(session)
    prefs = _experience_preferences(session)
    if facts.destination:
        prints[SEARCH_EXPERIENCE] = "|".join((facts.destination, *prefs))
    flight_fp = _flight_fingerprint(session)
    if flight_fp:
        prints[SEARCH_FLIGHT] = flight_fp
    del tasks
    return prints


def _explicit_search_kinds(session: AgentSession) -> set[str]:
    kinds: set[str] = set()
    tasks = session.projection.get("tasks")
    if isinstance(tasks, list):
        for item in tasks:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind") or "")
            provenance = str(item.get("provenance") or "")
            if provenance != "explicit" and item.get("accepted") is not True:
                continue
            if kind == "hotel":
                kinds.add("hotel")
            elif kind == "parking":
                kinds.add("parking")
            elif kind == "experience":
                kinds.add("experience")
            elif kind == "flight":
                kinds.add("flight")
    if _parking_led(session):
        kinds.add("parking")
    if _stay_explicit(session):
        kinds.add("hotel")
    experience = session.domains.get("experience")
    if isinstance(experience, dict) and (
        experience.get("accepted") is True or str(experience.get("provenance") or "") == "explicit"
    ):
        kinds.add("experience")
    flight = session.domains.get("flight")
    if isinstance(flight, dict) and (
        flight.get("accepted") is True or str(flight.get("provenance") or "") == "explicit"
    ):
        kinds.add("flight")
    return kinds


def _stay_window(session: AgentSession, facts: object | None = None) -> tuple[str, str]:
    if facts is None:
        _tasks, facts = snapshots_from_projection(session.projection)
        del _tasks
    start = session.stay_draft_start or str(getattr(facts, "start_date", "") or "")
    end = session.stay_draft_end or str(getattr(facts, "end_date", "") or "")
    if (not start or not end) and isinstance(facts, dict):
        start = start or str(facts.get("startDate") or "")
        end = end or str(facts.get("endDate") or "")
    if not start or not end:
        parking_start = _parking_calendar_day(session, "start")
        parking_end = _parking_calendar_day(session, "end")
        start = start or parking_start
        end = end or parking_end
    return start[:10], end[:10]


def _parking_calendar_day(session: AgentSession, field_id: str) -> str:
    parking = session.domains.get("parking")
    fields = parking.get("fields") if isinstance(parking, dict) else {}
    held = fields.get(field_id) if isinstance(fields, dict) else None
    value = str(held.get("value") or "") if isinstance(held, dict) else ""
    return value[:10] if len(value) >= 10 else ""


def _stay_facts_ready(session: AgentSession) -> bool:
    tasks, facts = snapshots_from_projection(session.projection)
    del tasks
    start, end = _stay_window(session, facts)
    return bool(facts.destination and start and end)


def _search_blocked(session: AgentSession) -> bool:
    kinds = _explicit_search_kinds(session)
    if "hotel" in kinds and not _stay_facts_ready(session):
        return True
    if "parking" in kinds and not (
        _parking_search_ready(session) or _parking_has_fresh_offers(session)
    ):
        parking = session.domains.get("parking")
        missing = parking.get("missing") if isinstance(parking, dict) else []
        if isinstance(missing, list) and missing:
            return True
        if not _parking_search_ready(session) and not _parking_has_fresh_offers(session):
            return True
    return False


def _parking_has_fresh_offers(session: AgentSession) -> bool:
    parking = session.domains.get("parking")
    if not isinstance(parking, dict):
        return False
    offer_held = parking.get("offerSet")
    offer = offer_held if isinstance(offer_held, dict) else {}
    snapshot = offer.get("snapshot")
    return (
        isinstance(snapshot, dict)
        and bool(snapshot.get("offers"))
        and offer.get("stale") is not True
    )


def _ready_search_capabilities(session: AgentSession) -> list[str]:
    ready: list[str] = []
    kinds = _explicit_search_kinds(session)
    tasks, facts = snapshots_from_projection(session.projection)
    established = established_capabilities(tasks, facts)
    if "hotel" in kinds and Capability.STAY_SEARCH in established:
        ready.append(SEARCH_STAY)
    if "parking" in kinds and (
        _parking_search_ready(session) or _parking_has_fresh_offers(session)
    ):
        ready.append(SEARCH_PARKING)
    if "experience" in kinds and Capability.EXPERIENCE_SEARCH in established:
        ready.append(SEARCH_EXPERIENCE)
    if "flight" in kinds and _flight_search_ready(session):
        ready.append(SEARCH_FLIGHT)
    return ready


def _fresh_result(session: AgentSession, capability: str, fingerprint: str) -> bool:
    if not fingerprint:
        return False
    if capability == SEARCH_STAY:
        current = session.stay_search
        return (
            fingerprint == session.stay_search_fingerprint
            and isinstance(current, dict)
            and current.get("stale") is not True
            and current.get("status") == "ok"
        )
    if capability == SEARCH_PARKING:
        return _parking_has_fresh_offers(session) and fingerprint == _parking_fingerprint(session)
    if capability == SEARCH_EXPERIENCE:
        current = session.experience_search
        return (
            fingerprint == session.experience_search_fingerprint
            and isinstance(current, dict)
            and current.get("stale") is not True
        )
    if capability == SEARCH_FLIGHT:
        current = session.flight_search
        return (
            fingerprint == session.flight_search_fingerprint
            and isinstance(current, dict)
            and current.get("stale") is not True
            and current.get("status") == "ok"
        )
    return False


def _invalidate_stale_searches(session: AgentSession, prints: Mapping[str, str]) -> None:
    stay_fp = prints.get(SEARCH_STAY, "")
    if (
        session.stay_search is not None
        and session.stay_search_fingerprint
        and stay_fp != session.stay_search_fingerprint
    ):
        current = dict(session.stay_search)
        if current.get("offers"):
            current["stale"] = True
            session.stay_search = current
            stay = session.domains.get("stay")
            if isinstance(stay, dict):
                stay["completeness"] = "stale"
    exp_fp = prints.get(SEARCH_EXPERIENCE, "")
    if (
        session.experience_search is not None
        and session.experience_search_fingerprint
        and exp_fp != session.experience_search_fingerprint
    ):
        current = dict(session.experience_search)
        if current.get("offers"):
            current["stale"] = True
            session.experience_search = current
    flight_fp = prints.get(SEARCH_FLIGHT, "")
    if (
        session.flight_search is not None
        and session.flight_search_fingerprint
        and flight_fp != session.flight_search_fingerprint
    ):
        current = dict(session.flight_search)
        if current.get("offers"):
            current["stale"] = True
            session.flight_search = current


def _replace_last_agent_turn(session: AgentSession, text: str) -> None:
    cleaned = text.strip()
    session.buyer_safe_message = cleaned
    if not cleaned:
        return
    if session.transcript and session.transcript[-1].get("role") == "agent":
        session.transcript[-1] = {
            **session.transcript[-1],
            "text": cleaned,
        }
        return
    _append_agent_turn(session, cleaned)


def _apply_airport_reply(session: AgentSession) -> None:
    last = _last_user_text(session)
    if not last or len(last.strip()) > 40:
        return
    code = resolve_airport_reply(last)
    if not code:
        return
    parking = session.domains.get("parking")
    if isinstance(parking, dict) and (
        parking.get("accepted") is True or str(parking.get("provenance") or "") == "explicit"
    ):
        fields = parking.get("fields") if isinstance(parking.get("fields"), dict) else {}
        if _empty_field(fields, "airportCode"):
            apply_patch(
                parking,
                "airportCode",
                code,
                source="current_turn",
                provenance="explicit",
            )
            apply_defaults(parking)
            refresh_completeness(
                parking,
                str(session.pending_authorization["gate"])
                if session.pending_authorization
                else None,
            )
            _localize_parking_asks(session)
    facts = session.projection.get("facts") if isinstance(session.projection, dict) else {}
    origin_city = str(facts.get("originCity") or "") if isinstance(facts, dict) else ""
    dest_city = str(facts.get("destination") or "") if isinstance(facts, dict) else ""
    origin_codes = airport_candidates_for_city(origin_city)
    dest_codes = airport_candidates_for_city(dest_city)
    if _heading_to_flight_airport(last) and isinstance(facts, dict):
        facts["destinationAirport"] = code
        session.answers["destinationAirport"] = code
        return
    if (
        isinstance(facts, dict)
        and not str(facts.get("departureAirport") or "").strip()
        and (code in origin_codes or (code not in dest_codes and not origin_codes))
    ):
        facts["departureAirport"] = code
        session.answers["departureAirport"] = code


def _dispatch_parking_search(request: Request, session: AgentSession) -> None:
    parking = session.domains.get("parking")
    if not isinstance(parking, dict):
        return
    snapshot = _grant_a2(request, session, parking)
    fields = parking.get("fields") if isinstance(parking.get("fields"), dict) else {}
    start_held = fields.get("start") if isinstance(fields, dict) else None
    end_held = fields.get("end") if isinstance(fields, dict) else None
    if isinstance(snapshot, dict):
        if isinstance(start_held, dict) and start_held.get("value"):
            snapshot["windowStart"] = str(start_held["value"])
        if isinstance(end_held, dict) and end_held.get("value"):
            snapshot["windowEnd"] = str(end_held["value"])
    offer = parking.setdefault("offerSet", {})
    if isinstance(offer, dict):
        offer["snapshot"] = snapshot
        offer["stale"] = False
        offer["intentId"] = snapshot.get("intentId")
    parking["intentId"] = snapshot.get("intentId")
    _refresh_pending(session)


def _reconcile_search_authorization(request: Request, session: AgentSession) -> None:
    last = _last_user_text(session)
    _ensure_stay_destination(session)
    prints = _current_search_fingerprints(session)
    _invalidate_stale_searches(session, prints)
    if isinstance(session.pending_date_cascade, dict):
        note = session.last_refinement_note or ""
        session.pending_search_authorization = None
        session.auto_search = []
        if note:
            _replace_last_agent_turn(session, note)
        session.last_refinement_note = ""
        return
    auto = tuple(session.auto_search)
    session.auto_search = []
    prior = session.pending_search_authorization
    confirmed: tuple[str, ...] | None = None
    if auto:
        confirmed = auto
        session.pending_search_authorization = None
    elif fingerprints_match(prior, prints):
        confirmed = match_confirmation(last, prior)
    else:
        session.pending_search_authorization = None
    try:
        if confirmed:
            _dispatch_capability_searches(request, session, confirmed)
            session.pending_search_authorization = None
            note = results_copy(
                confirmed,
                {
                    "stay": session.stay_search or {},
                    "parking": session.domains.get("parking") or {},
                    "experience": session.experience_search or {},
                    "flight": session.flight_search or {},
                },
                execution=session.search_execution,
            )
            refine = session.last_refinement_note
            if refine:
                note = f"{refine} {note}".strip() if note else refine
            if note:
                if _rental_explicit(session):
                    note = f"{note} {RENTAL_NO_ADAPTER_COPY}".strip()
                _replace_last_agent_turn(session, note)
            _refresh_pending(session)
            return
        if _search_blocked(session):
            _replace_with_authorized_copy(session)
            return
        ready = _ready_search_capabilities(session)
        needed = [
            capability
            for capability in ready
            if not _fresh_result(session, capability, prints.get(capability, ""))
        ]
        if not needed:
            _replace_with_authorized_copy(session)
            return
        pending = build_pending(needed, prints, place=_search_place(session))
        session.pending_search_authorization = pending
        prompt = str(pending.get("prompt") or "")
        if prompt:
            note = session.last_refinement_note
            combined = _join_distinct_copy(note, prompt)
            extra = _flight_follow_up(session)
            ask = _next_catalog_ask(session)
            parking_ask = ask if ask and SEARCH_PARKING not in needed else ""
            combined = _join_distinct_copy(combined, extra, parking_ask)
            _replace_last_agent_turn(session, combined)
        else:
            _replace_with_authorized_copy(session)
    finally:
        session.last_refinement_note = ""


_SEARCH_READY_CLAIM = re.compile(
    r"i have what i need to search|shall i search",
    re.I,
)
_FLIGHT_ACCEPT_RE = re.compile(
    r"\b(search (?:the )?flights?|include flights?|yes.{0,24}flights?|"
    r"help with (?:a |the )?flights?|want (?:a |the )?flights?|"
    r"add (?:the )?flights?|book (?:the )?flights?)\b",
    re.I,
)
_FLIGHT_OFFER_ASK_RE = re.compile(r"should i search flights", re.I)
_FLIGHT_PREFS_ANY = re.compile(
    r"\b(any(?:thing)?(?: is)? fine|no preference|no preference|doesn't matter|"
    r"does not matter|whatever|no airline|anytime)\b",
    re.I,
)
_FLIGHT_PREFS_REPLY_RE = re.compile(
    r"\b(direct(?: only)?|non[-\s]?stop|connections?|morning|afternoon|evening|"
    r"anytime|night|airline|airlines|air\s+india|cabin|business|economy)\b",
    re.I,
)
_FLIGHT_PREFS_COPY = (
    "For the flight, do you have a preferred departure time, and should I keep it "
    "direct only or include connections? Any airline preference is optional."
)
_FLIGHT_CITY_CODES = {
    "new york": "NYC",
    "nyc": "NYC",
    "london": "LON",
    "manchester": "MAN",
    "edinburgh": "EDI",
    "heathrow": "LHR",
    "gatwick": "LGW",
    "stansted": "STN",
    "milan": "MXP",
    "mumbai": "BOM",
    "dubai": "DXB",
}
_FLIGHT_METRO_CODES = {
    "new york": "NYC",
    "nyc": "NYC",
    "london": "LON",
    "dubai": "DXB",
}
_FLIGHT_METRO_IATA = frozenset(_FLIGHT_METRO_CODES.values())
_ALL_AIRPORTS_RE = re.compile(
    r"\b(all airports|every airport|any airport|all of them|search (?:them )?all|"
    r"both cities)\b",
    re.I,
)
_AIRPORT_CHOICE_ASK_RE = re.compile(
    r"which airports should i search|all airports in",
    re.I,
)
_ALL_AIRPORTS_REPLY_RE = re.compile(
    r"^\s*(all(?:\s+airports?)?|all of them|those|them|either|both(?: cities)?|"
    r"any(?: airport| of them)?|everywhere|every airport|"
    r"(?:it )?does(?: n[o']?t)? matter|whatever|search (?:them )?all)\s*[.!]?\s*$",
    re.I,
)
_FLIGHT_PAIR_RE = re.compile(
    r"\b([A-Za-z]{3})\s*(?:to|-|→)\s*([A-Za-z]{3})\b",
)
_FLIGHT_TO_RE = re.compile(
    r"\b(?:a\s+)?(?:flight|flights|fly)\s+to\b",
    re.I,
)
_GENERIC_AFFIRM_RE = re.compile(
    r"^(?:yes|yeah|yep|yup|ok|okay|sure)(?: please)?$",
    re.I,
)


def _heading_to_flight_airport(text: str) -> bool:
    if _FLIGHT_TO_RE.search(text) is None:
        return False
    return re.search(r"\bfrom\b", text, re.I) is None


def _canonicalize_session_dates(session: AgentSession) -> None:
    facts = session.projection.get("facts") if isinstance(session.projection, dict) else {}
    if not isinstance(facts, dict):
        return
    start = str(facts.get("startDate") or "")
    end = str(facts.get("endDate") or "")
    if start:
        facts["startDate"] = rewrite_past_iso_if_year_omitted(start, session.objective)
    if end:
        facts["endDate"] = rewrite_past_iso_if_year_omitted(end, session.objective)
    start = str(facts.get("startDate") or "")
    end = str(facts.get("endDate") or "")
    if start and end:
        facts["dates"] = f"{start} to {end}" if start != end else start
        facts["hasExactDates"] = True
    elif not start or not end:
        parking_start = _parking_calendar_day(session, "start")
        parking_end = _parking_calendar_day(session, "end")
        if parking_start and parking_end:
            facts["startDate"] = parking_start
            facts["endDate"] = parking_end
            facts["dates"] = f"{parking_start} to {parking_end}"
            facts["hasExactDates"] = True
            start, end = parking_start, parking_end
    if session.answers.get("startDate"):
        session.answers["startDate"] = str(facts.get("startDate") or session.answers["startDate"])
    if session.answers.get("endDate"):
        session.answers["endDate"] = str(facts.get("endDate") or session.answers["endDate"])
    parking = session.domains.get("parking")
    fields = parking.get("fields") if isinstance(parking, dict) else None
    if isinstance(fields, dict):
        for key in ("start", "end"):
            held = fields.get(key)
            if isinstance(held, dict) and isinstance(held.get("value"), str):
                held["value"] = rewrite_past_iso_if_year_omitted(
                    str(held["value"]), session.objective
                )
    date_held = _flight_field(session, "date")
    if date_held:
        rewritten = rewrite_past_iso_if_year_omitted(date_held, session.objective)
        flight = session.domains.get("flight")
        flight_fields = flight.get("fields") if isinstance(flight, dict) else None
        if isinstance(flight_fields, dict) and isinstance(flight_fields.get("date"), dict):
            flight_fields["date"]["value"] = rewritten[:10]
    date_end_held = _flight_field(session, "dateEnd")
    if date_end_held:
        rewritten_end = rewrite_past_iso_if_year_omitted(date_end_held, session.objective)
        flight = session.domains.get("flight")
        flight_fields = flight.get("fields") if isinstance(flight, dict) else None
        if isinstance(flight_fields, dict) and isinstance(flight_fields.get("dateEnd"), dict):
            flight_fields["dateEnd"]["value"] = rewritten_end[:10]


def _user_turn_count(session: AgentSession) -> int:
    return sum(1 for item in session.transcript if item.get("role") == "user")


def _is_opening_intent_turn(session: AgentSession) -> bool:
    return _user_turn_count(session) <= 1


def _flight_city_code(name: str) -> str:
    cleaned = re.sub(r"[^a-z]+", " ", name.lower()).strip()
    return _FLIGHT_CITY_CODES.get(cleaned, "")


def _flight_metro_or_primary(city: str) -> str:
    cleaned = re.sub(r"[^a-z]+", " ", city.lower()).strip()
    if cleaned in _FLIGHT_METRO_CODES:
        return _FLIGHT_METRO_CODES[cleaned]
    candidates = airport_candidates_for_city(city)
    if candidates:
        return candidates[0]
    return _flight_city_code(city)


def _unique_flight_code(city: str, raw: str) -> str:
    for token in (raw, city):
        cleaned = str(token or "").strip()
        if not cleaned:
            continue
        named = resolve_airport_reply(cleaned) or (normalize_iata(cleaned) or "")
        if named and named not in _FLIGHT_METRO_IATA:
            return named
        candidates = airport_candidates_for_city(cleaned)
        if len(candidates) == 1:
            return candidates[0]
    candidates = airport_candidates_for_city(city)
    raw_upper = raw.strip().upper()
    if raw_upper in candidates:
        return raw_upper
    if len(candidates) > 1:
        return ""
    if len(candidates) == 1:
        return candidates[0]
    code = _flight_city_code(city)
    if code in _FLIGHT_METRO_IATA:
        return ""
    if code:
        return code
    mapped = _flight_city_code(raw)
    if mapped in _FLIGHT_METRO_IATA:
        return ""
    if mapped:
        return mapped
    if (
        len(raw_upper) == 3
        and raw_upper.isalpha()
        and raw_upper in _known_flight_iata()
        and raw_upper not in _FLIGHT_METRO_IATA
    ):
        return raw_upper
    return ""


def _flight_route_cities(session: AgentSession) -> tuple[str, str]:
    facts = session.projection.get("facts") if isinstance(session.projection, dict) else {}
    if not isinstance(facts, dict):
        facts = {}
    origin = str(facts.get("originCity") or "").strip() or _flight_field(session, "origin")
    dest = str(facts.get("destination") or "").strip() or _flight_field(session, "destination")
    if not origin:
        origin = str(facts.get("departureAirport") or "").strip()
    if not dest:
        dest = str(facts.get("destinationAirport") or "").strip()
    return origin, dest


def _parking_airport_code(session: AgentSession) -> str:
    parking = session.domains.get("parking")
    fields = parking.get("fields") if isinstance(parking, dict) else {}
    held = fields.get("airportCode") if isinstance(fields, dict) else None
    if isinstance(held, dict):
        return str(held.get("value") or "").strip().upper()
    return ""


def _suggested_flight_airports(session: AgentSession) -> tuple[str, str]:
    origin_city, dest_city = _flight_route_cities(session)
    origin_codes = airport_candidates_for_city(origin_city)
    dest_codes = airport_candidates_for_city(dest_city)
    parking = _parking_airport_code(session)
    origin = origin_codes[0] if origin_codes else _flight_metro_or_primary(origin_city)
    if parking and (not dest_codes or parking in dest_codes):
        dest = parking
    elif dest_codes:
        dest = dest_codes[0]
    else:
        dest = _flight_metro_or_primary(dest_city)
    return origin, dest


def _known_flight_iata() -> frozenset[str]:
    codes = set(KNOWN_IATA)
    codes.update(_FLIGHT_METRO_IATA)
    codes.update(_FLIGHT_CITY_CODES.values())
    codes.update(AIRPORT_CHOICE_LABELS)
    for city in (
        "london",
        "new york",
        "nyc",
        "dubai",
        "manchester",
        "edinburgh",
        "glasgow",
        "amsterdam",
        "paris",
        "dublin",
    ):
        codes.update(airport_candidates_for_city(city))
    return frozenset(codes)


def _parse_flight_airport_pair(text: str) -> tuple[str, str]:
    known = _known_flight_iata()
    pair = _FLIGHT_PAIR_RE.search(text)
    if pair:
        origin = pair.group(1).upper()
        dest = pair.group(2).upper()
        if origin in known and dest in known:
            return origin, dest
    split = re.search(r"(.+?)\s+to\s+(.+)", text, re.I)
    if split:
        origin = resolve_airport_reply(split.group(1).strip())
        dest = resolve_airport_reply(split.group(2).strip())
        if not origin:
            token = split.group(1).strip().upper()
            origin = token if token in known else ""
        if not dest:
            token = split.group(2).strip().upper()
            dest = token if token in known else ""
        if origin and dest:
            return origin, dest
    return "", ""


def _last_agent_text(session: AgentSession) -> str:
    for item in reversed(session.transcript):
        if item.get("role") == "agent":
            return str(item.get("text") or "")
    return str(session.buyer_safe_message or "")


def _prior_agent_text(session: AgentSession) -> str:
    texts = [
        str(item.get("text") or "")
        for item in session.transcript
        if item.get("role") == "agent" and str(item.get("text") or "").strip()
    ]
    if len(texts) >= 2:
        return texts[-2]
    if texts:
        return texts[-1]
    return ""


def _flight_airport_ask_pending(session: AgentSession) -> bool:
    blob = f"{_prior_agent_text(session)} {_last_agent_text(session)}"
    return _AIRPORT_CHOICE_ASK_RE.search(blob) is not None


def _validated_route_iata(city: str, code: str) -> str:
    upper = code.strip().upper()
    if not upper or len(upper) != 3 or not upper.isalpha():
        return ""
    if upper not in _known_flight_iata():
        return ""
    candidates = airport_candidates_for_city(city)
    metro = _flight_metro_or_primary(city)
    if metro and upper == metro:
        return upper
    if candidates:
        return upper if upper in candidates else ""
    mapped = _flight_city_code(city)
    if mapped and upper == mapped:
        return upper
    return upper if not city.strip() else ""


def _airports_from_plan_turn(
    plan_turn: Mapping[str, object] | None, origin_city: str, dest_city: str
) -> tuple[str, str]:
    if not isinstance(plan_turn, Mapping):
        return "", ""
    facts = plan_turn.get("facts")
    if not isinstance(facts, Mapping):
        return "", ""
    origin = _validated_route_iata(origin_city, str(facts.get("departureAirport") or ""))
    dest = _validated_route_iata(dest_city, str(facts.get("destinationAirport") or ""))
    return origin, dest


def _set_flight_airports(session: AgentSession, origin: str, dest: str, *, source: str) -> None:
    if not origin or not dest:
        return
    _ensure_flight_domain(session)
    flight = session.domains["flight"]
    fields = flight.setdefault("fields", {})
    if not isinstance(fields, dict):
        fields = {}
        flight["fields"] = fields
    fields["origin"] = {"value": origin, "source": source, "provenance": "explicit"}
    fields["destination"] = {"value": dest, "source": source, "provenance": "explicit"}
    facts = session.projection.get("facts") if isinstance(session.projection, dict) else {}
    if isinstance(facts, dict):
        facts["departureAirport"] = origin
        facts["destinationAirport"] = dest
    session.answers["departureAirport"] = origin
    session.flight_airports_resolved = True


def _set_flight_destination_only(session: AgentSession, dest: str, *, source: str) -> None:
    if not dest:
        return
    _ensure_flight_domain(session)
    flight = session.domains["flight"]
    fields = flight.setdefault("fields", {})
    if not isinstance(fields, dict):
        fields = {}
        flight["fields"] = fields
    fields["destination"] = {"value": dest, "source": source, "provenance": "explicit"}
    facts = session.projection.get("facts") if isinstance(session.projection, dict) else {}
    if isinstance(facts, dict):
        facts["destinationAirport"] = dest
    session.flight_airports_resolved = False


def _apply_flight_airport_reply(
    session: AgentSession, *, plan_turn: Mapping[str, object] | None = None
) -> None:
    if "flight" not in _explicit_search_kinds(session):
        return
    if session.flight_airports_resolved and _flight_search_ready(session):
        return
    if _is_opening_intent_turn(session):
        return
    last = _last_user_text(session)
    if not last or _GENERIC_AFFIRM_RE.fullmatch(last.strip()):
        return
    origin_only = _session_refinement(session)
    if origin_only is not None and origin_only.flight_origin and not origin_only.flight_destination:
        return
    if (
        origin_only is not None
        and origin_only.parking_airport
        and not (origin_only.flight_origin or origin_only.flight_destination)
    ):
        return
    if re.search(r"\bparking\b", last, re.I):
        return
    origin_city, dest_city = _flight_route_cities(session)
    asked = _flight_airport_ask_pending(session)
    if _ALL_AIRPORTS_RE.search(last) or (asked and _ALL_AIRPORTS_REPLY_RE.fullmatch(last.strip())):
        origin = _flight_metro_or_primary(origin_city)
        dest = _flight_metro_or_primary(dest_city)
        _set_flight_airports(session, origin, dest, source="current_turn")
        return
    pair_origin, pair_dest = _parse_flight_airport_pair(last)
    if pair_origin and pair_dest:
        origin = _validated_route_iata(origin_city, pair_origin) or pair_origin
        dest = _validated_route_iata(dest_city, pair_dest) or pair_dest
        if origin in _known_flight_iata() and dest in _known_flight_iata():
            _set_flight_airports(session, origin, dest, source="current_turn")
            return
    code = resolve_airport_reply(last)
    if not code:
        token = re.sub(r"[^A-Za-z]+", "", last).upper()
        if token in _known_flight_iata():
            code = token
    if code:
        origin_codes = airport_candidates_for_city(origin_city)
        dest_codes = airport_candidates_for_city(dest_city)
        parking = _parking_airport_code(session)
        origin = _flight_field(session, "origin")
        dest = _flight_field(session, "destination")
        dest_specific = bool(dest) and dest not in _FLIGHT_METRO_IATA
        origin_missing = not origin or origin in _FLIGHT_METRO_IATA
        heading_to = _heading_to_flight_airport(last)
        if heading_to:
            dest = code
            origin = origin or (
                origin_codes[0] if origin_codes else _flight_metro_or_primary(origin_city)
            )
            if origin and dest:
                _set_flight_airports(session, origin, dest, source="current_turn")
                return
            _set_flight_destination_only(session, dest, source="current_turn")
            return
        if dest_specific and origin_missing and code != dest:
            origin = code
        elif code in dest_codes or code == parking:
            dest = code
            origin = origin or (
                origin_codes[0] if origin_codes else _flight_metro_or_primary(origin_city)
            )
        elif code in origin_codes:
            origin = code
            if not dest:
                if parking in dest_codes:
                    dest = parking
                elif dest_codes:
                    dest = dest_codes[0]
                else:
                    dest = _flight_metro_or_primary(dest_city)
        else:
            origin, dest = "", ""
        if origin and dest:
            _set_flight_airports(session, origin, dest, source="current_turn")
            return
    model_origin, model_dest = _airports_from_plan_turn(plan_turn, origin_city, dest_city)
    if asked and (model_origin or model_dest):
        origin = model_origin or _flight_metro_or_primary(origin_city)
        dest = model_dest or _flight_metro_or_primary(dest_city)
        _set_flight_airports(session, origin, dest, source="current_turn")


def _flight_airport_choice_copy(session: AgentSession) -> str:
    origin_city, dest_city = _flight_route_cities(session)
    if not origin_city or not dest_city:
        return "I still need a clear origin and destination for the flight before I can search it."
    origin, dest = _suggested_flight_airports(session)
    origin_label = AIRPORT_CHOICE_LABELS.get(origin, origin or origin_city)
    dest_label = AIRPORT_CHOICE_LABELS.get(dest, dest or dest_city)
    parking = _parking_airport_code(session)
    parking_note = ""
    if parking and parking == dest:
        parking_note = f" Parking is at {AIRPORT_CHOICE_LABELS.get(parking, parking)}."
    return (
        f"You said {origin_city} to {dest_city}.{parking_note} "
        f"Which airports should I search for the flight booking: "
        f"{origin_label} to {dest_label}, "
        f"or all airports in {origin_city} and {dest_city}?"
    )


def _flight_missing_endpoints_copy(session: AgentSession) -> str:
    origin_city, dest_city = _flight_route_cities(session)
    if origin_city and dest_city:
        return _flight_airport_choice_copy(session)
    return "I still need a clear origin and destination for the flight before I can search it."


def _seed_flight_from_facts(session: AgentSession, *, source: str) -> None:
    flight = session.domains.get("flight")
    facts = session.projection.get("facts")
    if not isinstance(flight, dict) or not isinstance(facts, dict):
        return
    fields = flight.setdefault("fields", {})
    if not isinstance(fields, dict):
        fields = {}
        flight["fields"] = fields
    origin_city = str(facts.get("originCity") or "").strip()
    dest_city = str(facts.get("destination") or "").strip()
    last = _last_user_text(session)
    heading_to = _heading_to_flight_airport(last)
    to_code = resolve_airport_reply(last) if heading_to else ""
    origin_raw = "" if heading_to else str(facts.get("departureAirport") or origin_city).strip()
    dest_raw = to_code or str(facts.get("destinationAirport") or dest_city).strip()
    origin_code = _unique_flight_code(origin_city, origin_raw)
    dest_code = _unique_flight_code(to_code if to_code else dest_city, dest_raw)
    specific = origin_code not in _FLIGHT_METRO_IATA and dest_code not in _FLIGHT_METRO_IATA
    if origin_code and dest_code and specific and not heading_to:
        session.flight_airports_resolved = True
    if session.flight_airports_resolved:
        origin_code = origin_code or _flight_metro_or_primary(origin_city)
        dest_code = dest_code or _flight_metro_or_primary(dest_city)
    date = str(facts.get("startDate") or "")[:10]
    date_end = str(facts.get("endDate") or "")[:10]
    if origin_code and _empty_field(fields, "origin"):
        fields["origin"] = {"value": origin_code, "source": source, "provenance": "inferred"}
    if dest_code and _empty_field(fields, "destination"):
        fields["destination"] = {"value": dest_code, "source": source, "provenance": "inferred"}
    if date and _empty_field(fields, "date"):
        fields["date"] = {"value": date, "source": source, "provenance": "inferred"}
    if date_end and _empty_field(fields, "dateEnd"):
        fields["dateEnd"] = {"value": date_end, "source": source, "provenance": "inferred"}
        if not session.flight_draft_end:
            session.flight_draft_end = date_end


def _flight_proposed(session: AgentSession) -> bool:
    tasks = session.projection.get("tasks")
    if not isinstance(tasks, list):
        return False
    for item in tasks:
        if (
            isinstance(item, dict)
            and item.get("kind") == "flight"
            and item.get("provenance") == "proposed"
        ):
            return item.get("accepted") is not True
    return False


def _accept_proposed_flight(session: AgentSession) -> None:
    last = _last_user_text(session)
    if not last:
        return
    asked = _FLIGHT_OFFER_ASK_RE.search(_last_agent_text(session)) is not None
    prefs = (
        _FLIGHT_PREFS_ANY.search(last) is not None
        or _FLIGHT_PREFS_REPLY_RE.search(last) is not None
    )
    if not (
        _FLIGHT_ACCEPT_RE.search(last)
        or flight_requested(last)
        or (asked and (_GENERIC_AFFIRM_RE.fullmatch(last.strip()) is not None or prefs))
        or (_flight_proposed(session) and prefs)
    ):
        return
    flight = session.domains.get("flight")
    if not isinstance(flight, dict):
        session.domains["flight"] = empty_domain("flight", provenance="explicit", accepted=True)
        flight = session.domains["flight"]
    flight["accepted"] = True
    flight["provenance"] = "explicit"
    tasks = session.projection.get("tasks")
    if isinstance(tasks, list):
        for item in tasks:
            if isinstance(item, dict) and item.get("kind") == "flight":
                item["accepted"] = True
                item["provenance"] = "explicit"
    _seed_flight_from_facts(session, source="current_turn")


def _resolve_flight_prefs(session: AgentSession) -> None:
    last = _last_user_text(session)
    if not last:
        return
    if _FLIGHT_PREFS_ANY.search(last) or _FLIGHT_PREFS_REPLY_RE.search(last):
        session.flight_prefs_resolved = True


def _flight_follow_up(session: AgentSession) -> str:
    pending = session.pending_search_authorization
    pending_caps = pending.get("capabilities") if isinstance(pending, dict) else []
    if "flight" in _explicit_search_kinds(session) and not _flight_search_ready(session):
        return _flight_missing_endpoints_copy(session)
    if _flight_airport_ask_pending(session) and session.flight_airports_resolved:
        return ""
    if isinstance(pending_caps, list) and pending_caps and SEARCH_FLIGHT not in pending_caps:
        return ""
    origin = _flight_field(session, "origin")
    dest = _flight_field(session, "destination")
    facts = session.projection.get("facts") if isinstance(session.projection, dict) else {}
    if not origin and isinstance(facts, dict):
        origin = str(facts.get("originCity") or facts.get("departureAirport") or "").strip()
    if not dest and isinstance(facts, dict):
        dest = str(facts.get("destination") or "").strip()
    date = _flight_field(session, "date") or (
        str(facts.get("startDate") or "")[:10] if isinstance(facts, dict) else ""
    )
    if _flight_proposed(session):
        if session.flight_prefs_resolved:
            return ""
        if not origin or not dest:
            return "It looks like this trip might need a flight. Where are you flying from and to?"
        where = f" from {origin} to {dest}"
        when = f" on {date}" if date else ""
        return (
            f"It looks like you're travelling{where}{when}. "
            "Should I search flights? If yes: "
            f"{_FLIGHT_PREFS_COPY}"
        )
    pending = session.pending_search_authorization
    pending_caps = pending.get("capabilities") if isinstance(pending, dict) else []
    if (
        "flight" in _explicit_search_kinds(session)
        and _flight_search_ready(session)
        and not session.flight_prefs_resolved
        and isinstance(pending_caps, list)
        and SEARCH_FLIGHT in pending_caps
    ):
        return _FLIGHT_PREFS_COPY
    if (
        "flight" in _explicit_search_kinds(session)
        and _flight_search_ready(session)
        and not session.flight_prefs_resolved
    ):
        return _FLIGHT_PREFS_COPY
    return ""


def _missing_search_copy(session: AgentSession) -> str:
    parts: list[str] = []
    if _stay_explicit(session) and not _stay_facts_ready(session):
        parts.append("I still need a destination and dates on the hotel before I can search it.")
    if "flight" in _explicit_search_kinds(session) and not _flight_search_ready(session):
        origin = _flight_field(session, "origin")
        dest = _flight_field(session, "destination")
        if not origin or not dest:
            parts.append(_flight_missing_endpoints_copy(session))
        elif not _flight_field(session, "date"):
            parts.append("I still need a flight date before I can search it.")
    experience = session.domains.get("experience")
    facts = session.projection.get("facts") if isinstance(session.projection, dict) else {}
    dest = str(facts.get("destination") or "") if isinstance(facts, dict) else ""
    if (
        isinstance(experience, dict)
        and (
            experience.get("accepted") is True
            or str(experience.get("provenance") or "") == "explicit"
        )
        and not dest
    ):
        parts.append("I still need a destination for things to do.")
    parking = session.domains.get("parking")
    missing = parking.get("missing") if isinstance(parking, dict) else []
    if isinstance(parking, dict) and isinstance(missing, list) and missing:
        ask = _next_catalog_ask(session)
        if ask:
            parts.append(ask)
    return " ".join(parts)


def _join_distinct_copy(*parts: str) -> str:
    combined = ""
    for part in parts:
        text = " ".join(str(part or "").split())
        if not text:
            continue
        if combined:
            if text.lower() in combined.lower():
                continue
            if combined.lower() in text.lower():
                combined = text
                continue
        combined = f"{combined} {text}".strip() if combined else text
    return combined


def _replace_with_authorized_copy(session: AgentSession) -> None:
    next_ask = _next_catalog_ask(session)
    flight_note = _flight_follow_up(session)
    pending = session.pending_search_authorization
    prompt = str(pending.get("prompt") or "") if isinstance(pending, dict) else ""
    claimed = _SEARCH_READY_CLAIM.search(session.buyer_safe_message or "") is not None
    if prompt:
        extra = flight_note
        combined = _join_distinct_copy(prompt, extra)
        _replace_last_agent_turn(session, combined)
        return
    if next_ask:
        missing = _missing_search_copy(session)
        combined = _join_distinct_copy(missing, next_ask, flight_note)
        _replace_last_agent_turn(session, combined)
        return
    if claimed:
        missing = _missing_search_copy(session)
        combined = _join_distinct_copy(missing, flight_note)
        if combined:
            _replace_last_agent_turn(session, combined)
        return
    if flight_note and _flight_proposed(session):
        current = (session.buyer_safe_message or "").strip()
        if flight_note not in current:
            _replace_last_agent_turn(
                session, f"{current} {flight_note}".strip() if current else flight_note
            )


def _flight_field(session: AgentSession, field_id: str) -> str:
    flight = session.domains.get("flight")
    fields = flight.get("fields") if isinstance(flight, dict) else {}
    if not isinstance(fields, dict):
        return ""
    held = fields.get(field_id)
    if not isinstance(held, dict):
        return ""
    return str(held.get("value") or "").strip()


def _flight_fingerprint(session: AgentSession) -> str:
    origin = _flight_field(session, "origin")
    destination = _flight_field(session, "destination")
    date = _flight_field(session, "date")
    date_end = _flight_field(session, "dateEnd") or session.flight_draft_end
    if not origin or not destination or not date:
        return ""
    return "|".join((origin, destination, date, date_end[:10] if date_end else date[:10]))


def _flight_search_ready(session: AgentSession) -> bool:
    return bool(_flight_fingerprint(session))


def _filter_stay_budget(session: AgentSession, public: dict[str, object]) -> dict[str, object]:
    limit = session.stay_max_amount_minor
    if limit is None:
        return public
    offers = public.get("offers")
    if not isinstance(offers, list):
        return public
    kept: list[object] = []
    for item in offers:
        if not isinstance(item, dict):
            continue
        price = item.get("price") if isinstance(item.get("price"), dict) else {}
        amount = price.get("amountMinor") if isinstance(price, dict) else None
        if isinstance(amount, int) and amount > limit:
            continue
        kept.append(item)
    public["offers"] = kept
    return public


def _search_flight_offers(request: Request, session: AgentSession) -> None:
    origin = _flight_field(session, "origin")
    destination = _flight_field(session, "destination")
    date = _flight_field(session, "date")
    date_end = (_flight_field(session, "dateEnd") or session.flight_draft_end or date)[:10]
    query = {
        "origin": origin,
        "destination": destination,
        "date": date,
        "dateEnd": date_end,
    }
    fingerprint = _flight_fingerprint(session)
    if fingerprint == session.flight_search_fingerprint and session.flight_search is not None:
        current = session.flight_search
        if isinstance(current, dict):
            current["stale"] = False
        return
    try:
        provider = _provider(request)
        result = provider.execute_turn(
            {
                "tool": "search_flight_offers",
                "payload": {
                    "origin": origin,
                    "destination": destination,
                    "date": date,
                    "correlationId": session.correlation_id,
                },
                "correlationId": session.correlation_id,
            }
        )
        inner = result.get("result") if isinstance(result, dict) else None
        if not isinstance(inner, dict):
            raise ApplicationError("flightSearch", "unavailable")
        public = dict(inner)
        public["stale"] = False
        public["query"] = query
    except ApplicationError:
        public = {
            "status": "unavailable",
            "label": "Sandbox flight search",
            "providerId": "liteapi-flights",
            "source": "sandbox",
            "query": query,
            "offers": [],
            "buyerSafeMessage": "Flight search is unavailable right now.",
            "bookingAuthority": "none",
            "stale": False,
        }
    session.flight_search = public
    session.flight_search_fingerprint = fingerprint


def _search_stay_offers(
    request: Request,
    session: AgentSession,
    destination: str,
    start: str,
    end: str,
    origin: str,
) -> None:
    fingerprint = "|".join((destination, start, end))
    if session.stay_max_amount_minor is not None:
        fingerprint = f"{fingerprint}|{session.stay_max_amount_minor}"
    if fingerprint == session.stay_search_fingerprint and session.stay_search is not None:
        current = session.stay_search
        if isinstance(current, dict):
            current["stale"] = False
        return
    previous = session.stay_search if isinstance(session.stay_search, dict) else None
    if previous is not None and previous.get("offers"):
        stale = dict(previous)
        stale["stale"] = True
        session.stay_search = stale
    payload: dict[str, object] = {
        "destination": destination,
        "checkIn": start[:10],
        "checkOut": end[:10],
        "origin": origin,
        "correlationId": session.correlation_id,
    }
    try:
        provider = _provider(request)
        result = provider.execute_turn(
            {
                "tool": "search_stay_offers",
                "payload": payload,
                "correlationId": session.correlation_id,
            }
        )
        inner = result.get("result") if isinstance(result, dict) else None
        if not isinstance(inner, dict):
            raise ApplicationError("staySearch", "unavailable")
        session.stay_rate_refs = _stay_rate_refs(inner)
        public = _filter_stay_budget(session, _public_stay_search(inner))
        public["query"] = {
            "domain": "stay",
            "destination": {"kind": "city", "value": destination},
            "checkIn": start[:10],
            "checkOut": end[:10],
        }
    except ApplicationError:
        if previous is not None and previous.get("offers"):
            public = dict(previous)
            public["stale"] = True
            public["buyerSafeMessage"] = (
                "Hotel results are stale after a requirement change. "
                "Search is unavailable right now. No simulated parking was substituted."
            )
        else:
            public = {
                "status": "unavailable",
                "label": "Hotel search",
                "providerId": "",
                "source": "sandbox",
                "query": {
                    "domain": "stay",
                    "destination": {"kind": "city", "value": destination},
                    "checkIn": start[:10],
                    "checkOut": end[:10],
                },
                "offers": [],
                "buyerSafeMessage": (
                    "Hotel search is unavailable right now. No simulated parking was substituted."
                ),
                "bookingAuthority": "none",
                "stale": False,
                "offerKind": "regular",
            }
    session.stay_search = public
    session.stay_search_fingerprint = fingerprint
    stay = session.domains.get("stay")
    if isinstance(stay, dict):
        stay["completeness"] = "stale" if public.get("stale") is True else "offers"
        offer = stay.get("offerSet")
        if isinstance(offer, dict):
            offer["stale"] = public.get("stale") is True
    session.tool_trace.append({"kind": "execute", "tool": "search_stay_offers"})


def _public_stay_search(raw: Mapping[str, object]) -> dict[str, object]:
    offers_in = raw.get("offers")
    offers: list[dict[str, object]] = []
    if isinstance(offers_in, list):
        for item in offers_in:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            lower = name.lower()
            if any(token in lower for token in ("skyshield", "parkdirect", "terminalflex")):
                continue
            price_raw = item.get("price")
            price = dict(price_raw) if isinstance(price_raw, dict) else {}
            price_out: dict[str, object] = {}
            if "currency" in price:
                price_out["currency"] = price["currency"]
            if "amountMinor" in price:
                price_out["amountMinor"] = price["amountMinor"]
            cancellation = item.get("cancellation")
            photo = item.get("photoUrl")
            hold_raw = item.get("sandboxHold")
            hold = dict(hold_raw) if isinstance(hold_raw, dict) else None
            offer: dict[str, object] = {
                "id": str(item.get("id") or ""),
                "name": name,
                "locality": str(item.get("locality") or ""),
                "checkIn": str(item.get("checkIn") or ""),
                "checkOut": str(item.get("checkOut") or ""),
                "price": price_out,
                "cancellation": cancellation if isinstance(cancellation, str) else None,
                "availability": str(item.get("availability") or ""),
                "bookingAuthority": "none",
                "offerKind": "regular",
            }
            if isinstance(photo, str) and photo.startswith("https://") and " " not in photo:
                offer["photoUrl"] = photo.strip()[:500]
            if hold is not None:
                offer["sandboxHold"] = {
                    "status": str(hold.get("status") or ""),
                    "bookingId": str(hold.get("bookingId") or "")[:80],
                    "simulatedPayment": hold.get("simulatedPayment") is True,
                }
            offers.append(offer)
    query_raw = raw.get("query")
    query = dict(query_raw) if isinstance(query_raw, dict) else None
    status = str(raw.get("status") or "ok")
    source = str(raw.get("source") or "fake")
    label = str(raw.get("label") or "")
    if not label:
        label = (
            "Sandbox hotel search"
            if source == "sandbox"
            else "Labelled fake hotel search"
            if source == "fake"
            else "Hotel search"
        )
    out: dict[str, object] = {
        "status": status,
        "label": label,
        "providerId": str(raw.get("providerId") or "liteapi"),
        "source": source,
        "query": query,
        "offers": offers,
        "buyerSafeMessage": str(raw.get("buyerSafeMessage") or label),
        "bookingAuthority": "none",
        "stale": False,
        "offerKind": "regular",
    }
    if isinstance(raw.get("fetchedAt"), str):
        out["fetchedAt"] = raw["fetchedAt"]
    warnings = raw.get("warnings")
    if isinstance(warnings, list):
        out["warnings"] = [str(item) for item in warnings if isinstance(item, str)]
    encoded = json.dumps(out).lower()
    if "x-api-key" in encoded or "itaa_liteapi_api_key" in encoded or '"rateref"' in encoded:
        raise ApplicationError("staySearch", "closed")
    return out


def _stay_rate_refs(raw: Mapping[str, object]) -> dict[str, str]:
    refs: dict[str, str] = {}
    offers_in = raw.get("offers")
    if not isinstance(offers_in, list):
        return refs
    for item in offers_in:
        if not isinstance(item, dict):
            continue
        offer_id = str(item.get("id") or "").strip()
        rate_ref = str(item.get("rateRef") or "").strip()
        if offer_id and rate_ref:
            refs[offer_id] = rate_ref
    return refs


def _experience_preferences(session: AgentSession) -> tuple[str, ...]:
    facts = session.projection.get("facts") if isinstance(session.projection, dict) else {}
    if not isinstance(facts, dict):
        return ()
    raw = facts.get("experiencePreferences")
    if isinstance(raw, list):
        return tuple(str(item).strip() for item in raw if str(item).strip())
    day = str(facts.get("dayPart") or "").strip().lower()
    if day in {"evening", "morning", "afternoon"}:
        return (day,)
    return ()


def _search_experience_offers(
    request: Request,
    session: AgentSession,
    destination: str,
    preferences: tuple[str, ...],
) -> None:
    fingerprint = "|".join((destination, *preferences))
    if (
        fingerprint == session.experience_search_fingerprint
        and session.experience_search is not None
    ):
        current = session.experience_search
        if isinstance(current, dict):
            current["stale"] = False
        return
    previous = session.experience_search if isinstance(session.experience_search, dict) else None
    if previous is not None and previous.get("offers"):
        stale = dict(previous)
        stale["stale"] = True
        session.experience_search = stale
    payload: dict[str, object] = {
        "destination": destination,
        "preferences": list(preferences),
        "correlationId": session.correlation_id,
    }
    try:
        provider = _provider(request)
        result = provider.execute_turn(
            {
                "tool": "search_experience_offers",
                "payload": payload,
                "correlationId": session.correlation_id,
            }
        )
        inner = result.get("result") if isinstance(result, dict) else None
        if not isinstance(inner, dict):
            raise ApplicationError("experienceSearch", "unavailable")
        public = _public_experience_search(inner)
    except ApplicationError:
        if previous is not None and previous.get("offers"):
            public = dict(previous)
            public["stale"] = True
            public["buyerSafeMessage"] = (
                "Experience results are stale after a requirement change. "
                "Search is unavailable right now. No hotel inventory was substituted."
            )
        else:
            public = {
                "status": "unavailable",
                "label": "Experience search",
                "providerId": "",
                "source": "sandbox",
                "query": {
                    "domain": "experience",
                    "destination": {"kind": "city", "value": destination},
                    "preferences": list(preferences),
                },
                "offers": [],
                "buyerSafeMessage": (
                    "Experience search is unavailable right now. "
                    "No hotel or parking inventory was substituted."
                ),
                "bookingAuthority": "none",
                "stale": False,
                "offerKind": "regular",
            }
    session.experience_search = public
    session.experience_search_fingerprint = fingerprint
    experience = session.domains.get("experience")
    if isinstance(experience, dict):
        experience["completeness"] = "stale" if public.get("stale") is True else "offers"
        offer = experience.get("offerSet")
        if isinstance(offer, dict):
            offer["stale"] = public.get("stale") is True
    session.tool_trace.append({"kind": "execute", "tool": "search_experience_offers"})


def _public_experience_search(raw: Mapping[str, object]) -> dict[str, object]:
    offers_in = raw.get("offers")
    offers: list[dict[str, object]] = []
    if isinstance(offers_in, list):
        for item in offers_in:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("name") or "").strip()
            if not title:
                continue
            lower = title.lower()
            if any(token in lower for token in ("skyshield", "parkdirect", "terminalflex")):
                continue
            price_raw = item.get("price")
            price = dict(price_raw) if isinstance(price_raw, dict) else {}
            price_out: dict[str, object] = {}
            if "currency" in price:
                price_out["currency"] = price["currency"]
            if "amountMinor" in price:
                price_out["amountMinor"] = price["amountMinor"]
            duration = item.get("durationMinutes")
            photo = item.get("photoUrl")
            offer: dict[str, object] = {
                "id": str(item.get("id") or ""),
                "title": title,
                "category": str(item.get("category") or "Experience"),
                "location": str(item.get("location") or ""),
                "availability": str(item.get("availability") or ""),
                "price": price_out,
                "durationMinutes": duration if isinstance(duration, int) else None,
                "cancellation": item.get("cancellation")
                if isinstance(item.get("cancellation"), str)
                else None,
                "bookingAuthority": "none",
                "offerKind": "regular",
            }
            if isinstance(photo, str) and photo.startswith("https://") and " " not in photo:
                offer["photoUrl"] = photo.strip()[:500]
            offers.append(offer)
    query_raw = raw.get("query")
    query = dict(query_raw) if isinstance(query_raw, dict) else None
    status = str(raw.get("status") or "ok")
    source = str(raw.get("source") or "fake")
    label = str(raw.get("label") or "")
    if not label:
        label = (
            "Sandbox experience search"
            if source == "sandbox"
            else "Labelled fake experience search"
            if source == "fake"
            else "Experience search"
        )
    out: dict[str, object] = {
        "status": status,
        "label": label,
        "providerId": str(raw.get("providerId") or "prioticket"),
        "source": source,
        "query": query,
        "offers": offers,
        "buyerSafeMessage": str(raw.get("buyerSafeMessage") or label),
        "bookingAuthority": "none",
        "stale": False,
        "offerKind": "regular",
    }
    if isinstance(raw.get("fetchedAt"), str):
        out["fetchedAt"] = raw["fetchedAt"]
    warnings = raw.get("warnings")
    if isinstance(warnings, list):
        out["warnings"] = [str(item) for item in warnings if isinstance(item, str)]
    encoded = json.dumps(out).lower()
    if (
        "itaa_prioticket_client_secret" in encoded
        or "client_secret" in encoded
        or "x-api-key" in encoded
        or "authorization: basic" in encoded
    ):
        raise ApplicationError("experienceSearch", "closed")
    return out


def _apply_stay_sandbox_hold(
    session: AgentSession, offer_id: str, result: Mapping[str, object]
) -> None:
    search = session.stay_search
    if not isinstance(search, dict) or not offer_id:
        return
    offers_in = search.get("offers")
    if not isinstance(offers_in, list):
        return
    updated: list[object] = []
    for item in offers_in:
        if not isinstance(item, dict) or str(item.get("id") or "") != offer_id:
            updated.append(item)
            continue
        offer = dict(item)
        offer["sandboxHold"] = {
            "status": str(result.get("status") or ""),
            "bookingId": str(result.get("bookingId") or "")[:80],
            "simulatedPayment": result.get("simulatedPayment") is True,
        }
        updated.append(offer)
    search["offers"] = updated
    note = str(result.get("buyerSafeMessage") or "")
    if note:
        _append_agent_turn(session, note)


def _parking_task(session: AgentSession) -> dict[str, object] | None:
    tasks = session.projection.get("tasks")
    if not isinstance(tasks, list):
        return None
    for item in tasks:
        if not isinstance(item, dict) or item.get("kind") != "parking":
            continue
        provenance = item.get("provenance")
        if provenance in {"explicit", "inferred"} or item.get("accepted") is True:
            return item
    return None


def _attach_parking_handoff(request: Request, session: AgentSession) -> None:
    parking = _parking_task(session)
    if parking is None:
        session.parking_handoff = {"path": PARKING_INTAKE_PATH, "support": None, "fields": {}}
        return
    prepared = _execute(
        request,
        session,
        _PREPARE_TOOL,
        {
            "objective": _provider_objective(session),
            "answers": dict(session.answers),
            "planConfirmed": True,
        },
    )
    if "intentId" in prepared or "buyerToken" in prepared:
        raise ApplicationError("internal", "closed")
    fields = _handoff_fields(prepared)
    previous = ""
    existing = session.parking_handoff
    if isinstance(existing, dict):
        raw_fields = existing.get("fields")
        if isinstance(raw_fields, dict):
            held = raw_fields.get("intakeId")
            if isinstance(held, str) and held.startswith("in_"):
                previous = held
    fields["intakeId"] = previous or register_agent_intake(request.app, session.correlation_id)
    session.parking_handoff = {
        "path": PARKING_INTAKE_PATH,
        "support": parking.get("support"),
        "fields": fields,
    }


@router.post(f"{PREFIX}/sessions")
def create_session(
    request: Request,
    body: Annotated[SessionCreateBody, Body()],
) -> dict[str, object]:
    if not body.objective.strip():
        raise ApplicationError("objective", "required")
    session = AgentSession(
        session_id=mint_opaque("as_"),
        objective=body.objective.strip(),
        answers={},
        correlation_id=_correlation(body.correlationId),
    )
    _append_user_turn(session, session.objective)
    _sessions(request)[session.session_id] = session
    _plan(request, session)
    return _public_session(session)


@router.post(f"{PREFIX}/sessions/{{session_id}}/turns")
def create_turn(
    request: Request,
    session_id: str,
    body: Annotated[SessionTurnBody, Body()],
) -> dict[str, object]:
    session = _require_session(request, session_id)
    if body.correlationId:
        session.correlation_id = _correlation(body.correlationId)
    has_answers = bool(body.answers)
    has_message = bool(body.message and body.message.strip())
    has_tool = bool(body.tool)
    has_patches = bool(body.patches)
    if not has_answers and not has_message and not has_tool and not has_patches:
        raise ApplicationError("payload", "schema_invalid")
    if has_tool:
        tool = body.tool or ""
        payload = dict(body.payload)
        if tool == "book_stay_sandbox":
            offer_id = str(payload.get("offerId") or "")
            payload["rateRef"] = session.stay_rate_refs.get(offer_id, "")
        result = _execute(request, session, tool, payload)
        if tool == "book_stay_sandbox":
            _apply_stay_sandbox_hold(session, str(payload.get("offerId") or ""), result)
        public = _public_session(session)
        public["result"] = result
        return public
    if has_patches:
        _apply_direct_patches(session, body.patches or [])
        if not has_message and not has_answers:
            return _public_session(session)
    _append_event(session, "PLAN_UPDATING", "Updating your plan")
    if has_answers:
        session.answers = _merge_answers(session.answers, body.answers or {})
    if has_message:
        note = (body.message or "").strip()
        _append_user_turn(session, note)
        session.extra_note = f"{session.extra_note} {note}".strip()
    _plan(request, session)
    if session.confirmed:
        _attach_parking_handoff(request, session)
    return _public_session(session)


@router.post(f"{PREFIX}/sessions/{{session_id}}/confirm")
def confirm_session(
    request: Request,
    session_id: str,
    body: Annotated[SessionConfirmBody, Body()],
) -> dict[str, object]:
    del body
    session = _require_session(request, session_id)
    if session.confirmed:
        return _public_session(session)
    session.confirmed = True
    _append_event(session, "PLAN_CONFIRMED", CONFIRMED_COPY)
    _attach_parking_handoff(request, session)
    _sync_domains(session, source="earlier_turn")
    _refresh_pending(session)
    return _public_session(session)


@router.post(f"{PREFIX}/sessions/{{session_id}}/grants")
def grant_session(
    request: Request,
    session_id: str,
    body: Annotated[SessionGrantBody, Body()],
) -> dict[str, object]:
    session = _require_session(request, session_id)
    pending = session.pending_authorization
    parking = session.domains.get("parking")
    if body.gate == "A2":
        if not isinstance(parking, dict) or parking.get("accepted") is not True:
            raise ApplicationError("parking", "illegal_state")
        if not _parking_search_ready(session):
            raise ApplicationError("approvalId", "required")
    else:
        if not isinstance(pending, dict) or pending.get("gate") != body.gate:
            raise ApplicationError("approvalId", "required")
        if body.domain != "parking" or pending.get("domain") != "parking":
            raise ApplicationError("domain", "closed")
        if not isinstance(parking, dict) or parking.get("accepted") is not True:
            raise ApplicationError("parking", "illegal_state")
    if body.gate == "A1":
        snapshot = _grant_a1(request, session, parking)
    elif body.gate == "A2":
        snapshot = _grant_a2(request, session, parking)
    elif body.gate == "A3":
        snapshot = _grant_a3(request, session, parking, body)
    elif body.gate == "A4":
        snapshot = _grant_a4(request, session, parking)
    else:
        raise ApplicationError("gate", "closed")
    offer = parking.setdefault("offerSet", {})
    if isinstance(offer, dict):
        offer["snapshot"] = snapshot
        offer["stale"] = False
        offer["intentId"] = snapshot.get("intentId")
    parking["intentId"] = snapshot.get("intentId")
    session.confirmed = True
    _refresh_pending(session)
    pending_now = session.pending_authorization
    if isinstance(pending_now, dict):
        _append_agent_turn(session, str(pending_now.get("prompt") or ""))
        _append_event(session, "AWAITING_HUMAN_APPROVAL", str(pending_now.get("prompt") or ""))
    return _public_session(session)


def _grant_a1(
    request: Request, session: AgentSession, parking: dict[str, object]
) -> dict[str, object]:
    del session
    fields = execution_fields(parking)
    created = create_owned_parking_intent(request, fields)
    intent_id = str(created.get("intentId") or "")
    parking["intentId"] = intent_id
    return confirm_intake_intent(request, intent_id, IntakeGateBody(confirm=True))


def _grant_a2(
    request: Request, session: AgentSession, parking: dict[str, object]
) -> dict[str, object]:
    intent_id = str(parking.get("intentId") or "")
    if not intent_id:
        snapshot = _grant_a1(request, session, parking)
        intent_id = str(parking.get("intentId") or snapshot.get("intentId") or "")
    if not intent_id:
        raise ApplicationError("intentId", "required")
    _append_event(session, "PARKING_RESEARCHING", "Researching suppliers")
    try:
        snapshot = dispatch_intake_intent(request, intent_id, IntakeGateBody(confirm=True))
    except ApplicationError as exc:
        if exc.field == "state" and exc.code == "illegal_state":
            snapshot = get_intake_intent(request, intent_id)
        else:
            raise
    _append_event(session, "OFFERS_COMPARING", "Comparing eligible offers")
    _append_event(session, "RECOMMENDATION_PREPARING", "Preparing recommendation")
    return snapshot


def _grant_a3(
    request: Request,
    session: AgentSession,
    parking: dict[str, object],
    body: SessionGrantBody,
) -> dict[str, object]:
    del session
    intent_id = str(parking.get("intentId") or "")
    offer_id = body.offerId
    if not offer_id:
        held = parking.get("offerSet")
        snapshot = held.get("snapshot") if isinstance(held, dict) else None
        if isinstance(snapshot, dict) and isinstance(snapshot.get("recommendedOfferId"), str):
            offer_id = str(snapshot["recommendedOfferId"])
    if not offer_id:
        raise ApplicationError("offerId", "required")
    return accept_intake_intent(
        request,
        intent_id,
        IntakeAcceptanceBody(offerId=offer_id, offerVersion=body.offerVersion),
    )


def _grant_a4(
    request: Request, session: AgentSession, parking: dict[str, object]
) -> dict[str, object]:
    del session
    intent_id = str(parking.get("intentId") or "")
    return authorize_intake_intent(
        request, intent_id, IntakeAuthorizationBody(mode="SIMULATED"), None
    )


@router.get(f"{PREFIX}/sessions/{{session_id}}")
def get_session(request: Request, session_id: str) -> dict[str, object]:
    return _public_session(_require_session(request, session_id))


def _format_sse(event: Mapping[str, object]) -> str:
    payload = json.dumps(
        {"kind": event.get("kind"), "message": event.get("message")},
        separators=(",", ":"),
        sort_keys=True,
    )
    kind = str(event.get("kind") or "message")
    sequence = event.get("sequence")
    return f"id: {sequence}\nevent: {kind}\ndata: {payload}\n\n"


def _event_stream(session: AgentSession) -> Iterator[str]:
    for event in session.events:
        yield _format_sse(event)


@router.get(f"{PREFIX}/sessions/{{session_id}}/events")
def session_events(request: Request, session_id: str) -> StreamingResponse:
    session = _require_session(request, session_id)
    return StreamingResponse(
        _event_stream(session),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
