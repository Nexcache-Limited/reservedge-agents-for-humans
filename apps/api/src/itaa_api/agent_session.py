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
    COMPETITION_PARKING_ONLY_COPY,
    RENTAL_NO_ADAPTER_COPY,
    apply_defaults,
    apply_model_patches,
    apply_patch,
    empty_domain,
    execution_fields,
    extract_conversation_patches,
    join_catalog_asks,
    mark_stale,
    overlay_time_on_instant,
    public_domain,
    refresh_completeness,
    sanitize_buyer_message,
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
        "book_stay_sandbox",
    }
)
PARKING_INTAKE_PATH = "/intents/new/parking"
FALLBACK_COPY = "Using the local planner (labelled)"
FAILED_COPY = "Could not complete this step"
CONFIRMED_COPY = "Plan confirmed"
REQUEST_OFFERS_PROMPT = (
    "I have everything I need for parking. "
    "Shall I request offers from 3 isolated simulated suppliers?"
)

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
        if kind not in {"parking", "rental", "hotel", "experience"}:
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
    _seed_parking_from_facts(session, source=source)
    _apply_extracted_patches(session, source=source)
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
    if not isinstance(parking, dict) or str(dest).lower() != "london":
        return
    asks = parking.get("ask")
    if not isinstance(asks, list):
        return
    for item in asks:
        if isinstance(item, dict) and item.get("id") == "airportCode":
            item["ask"] = "Which London airport do you need parking at?"


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
    last = _last_user_text(session)
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
        domain_key = "stay" if kind == "hotel" else kind
        domain = session.domains.get(domain_key)
        if not isinstance(domain, dict):
            continue
        field_id = str(patch.get("fieldId") or "")
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
    airport = facts.get("parkingAirport")
    if isinstance(airport, str) and airport and _empty_field(fields, "airportCode"):
        apply_patch(
            parking,
            "airportCode",
            airport,
            source=source,  # type: ignore[arg-type]
            provenance="explicit",
        )
    start_date = facts.get("startDate") if isinstance(facts.get("startDate"), str) else ""
    end_date = facts.get("endDate") if isinstance(facts.get("endDate"), str) else ""
    if start_date and _empty_field(fields, "start"):
        apply_patch(
            parking,
            "start",
            start_date,
            source=source,  # type: ignore[arg-type]
            provenance="explicit",
        )
    if end_date and _empty_field(fields, "end"):
        apply_patch(
            parking,
            "end",
            end_date,
            source=source,  # type: ignore[arg-type]
            provenance="explicit",
        )


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
        session.buyer_safe_message = prompt
        return
    intent_id = parking.get("intentId")
    resource_id = intent_id if isinstance(intent_id, str) and intent_id and not stale else None
    session.pending_authorization = {
        "gate": "A2",
        "domain": "parking",
        "prompt": REQUEST_OFFERS_PROMPT,
        "resourceId": resource_id,
    }
    parking["completeness"] = "awaiting_grant"
    session.buyer_safe_message = sanitize_buyer_message(
        REQUEST_OFFERS_PROMPT,
        a2_complete=False,
    )


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
    parts.append("Accept the recommended offer? Selection is not a booking.")
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
        "sharedBookingContext": _shared_booking_context(session),
        "workspace": {
            "persistence": "process-local",
            "note": (
                "Running and Pending are this browser session. "
                "API restart drops agent sessions; resume is not durable."
            ),
        },
    }


def _plan(request: Request, session: AgentSession) -> None:
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
    except ApplicationError as exc:
        _append_event(session, "FAILED_CLOSED", FAILED_COPY)
        raise exc
    except Exception:
        _append_event(session, "FAILED_CLOSED", FAILED_COPY)
        raise ApplicationError("model", "unavailable") from None
    _apply_plan_result(session, result)
    _dispatch_capability_searches(request, session)


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


def _dispatch_capability_searches(request: Request, session: AgentSession) -> None:
    """Invoke configured provider adapters for established Explicit capabilities.

    Destination plus dates never activates stay.search or experience.search. Unconfigured
    capabilities (rental.search) stay silent — no simulated substitute. Parking uses the
    existing simulated A1–A4 path, not this dispatcher.
    """

    tasks, facts = snapshots_from_projection(session.projection)
    for capability in established_capabilities(tasks, facts):
        tool = _CAPABILITY_TOOLS.get(capability)
        if tool == "search_stay_offers":
            _search_stay_offers(
                request,
                session,
                facts.destination,
                facts.start_date,
                facts.end_date,
                facts.origin_city,
            )
        elif tool == "search_experience_offers":
            prefs = _experience_preferences(session)
            _search_experience_offers(request, session, facts.destination, prefs)


def _search_stay_offers(
    request: Request,
    session: AgentSession,
    destination: str,
    start: str,
    end: str,
    origin: str,
) -> None:
    fingerprint = "|".join((destination, start, end))
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
        "checkIn": start,
        "checkOut": end,
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
        public = _public_stay_search(inner)
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
                    "checkIn": start,
                    "checkOut": end,
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
    note = str(public.get("buyerSafeMessage") or "")
    if note:
        _append_agent_turn(session, note)


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
    note = str(public.get("buyerSafeMessage") or "")
    if note:
        _append_agent_turn(session, note)


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
    _dispatch_capability_searches(request, session)
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
    if not isinstance(pending, dict) or pending.get("gate") != body.gate:
        raise ApplicationError("approvalId", "required")
    if body.domain != "parking" or pending.get("domain") != "parking":
        raise ApplicationError("domain", "closed")
    parking = session.domains.get("parking")
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
