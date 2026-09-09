"""Competition intake A1–A4. Server-minted governance. Never stores raw text."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Body, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from itaa_api.errors import (
    application_error_handler,
    http_exception_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from itaa_api.portfolio_http import (
    attach_portfolio_cookie,
    bucket_snapshots,
    portfolio_id_from,
)
from itaa_application.errors import ApplicationError
from itaa_application.golden_path import GoldenPathFacade
from itaa_application.portfolio import require_idempotency_key
from itaa_application.session_models import (
    AcceptCommand,
    AuthorizeCommand,
    BuyerSnapshot,
    GovernanceCommand,
)
from itaa_domain.errors import DomainInvariantError
from itaa_domain.identifiers import IntentId
from itaa_domain.value_objects import TimeWindow, format_utc, parse_utc

PREFIX = "/v1/simulations/airport-parking"
OPENAPI_TAG = "competition-intake"
INTENT_TTL = timedelta(hours=48)
SOLICITATION_TTL = timedelta(hours=24)
_CROCKFORD = "0123456789abcdefghjkmnpqrstvwxyz"
_EXTRACT_PATH = "/v1/google/extractions"
_DEFAULT_ADAPTER = "http://127.0.0.1:8080"
# Live Gemini may use the full 30s adapter deadline; keep BFF above that bound.
_EXTRACT_HTTP_TIMEOUT_S = 35.0

router = APIRouter()

ExtractClient = Callable[[dict[str, object]], dict[str, object]]


class ExtractionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    category: Literal["airport_parking"]


class ConfirmedIntentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intakeId: str
    airportCode: str
    start: str
    end: str
    vehicleClass: str
    covered: str
    shuttleMaxMinutes: int
    currency: str
    accessibility: list[Literal["step_free", "wheelchair", "ev_charging"]] = Field(
        default_factory=list
    )


class IntakeGateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: Literal[True] | None = None


class IntakeAcceptanceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    offerId: str
    offerVersion: int | None = Field(default=None, ge=1)


class IntakeAuthorizationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    acceptanceId: str | None = None
    amountMinor: int | None = Field(default=None, ge=0)
    currency: str | None = None
    supplierToken: str | None = None
    action: Literal["reserve_parking"] | None = None
    mode: Literal["SIMULATED"] | None = None


_EMPTY_GATE = IntakeGateBody()
_EMPTY_AUTHORIZATION = IntakeAuthorizationBody()


def mint_opaque(prefix: str) -> str:
    raw = secrets.token_bytes(26)
    return prefix + "".join(_CROCKFORD[byte % 32] for byte in raw)


def build_intake_app(
    facade: GoldenPathFacade,
    extract_client: ExtractClient | None = None,
) -> FastAPI:
    application = FastAPI(title="ITAA competition intake", docs_url=None, redoc_url=None)
    application.state.facade = facade
    application.state.extract_client = extract_client
    application.state.intake_records = {}
    application.state.competition_intents = {}
    application.include_router(router)
    application.add_exception_handler(ApplicationError, application_error_handler)  # type: ignore[arg-type]
    application.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    application.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    application.add_exception_handler(Exception, unhandled_error_handler)
    attach_portfolio_cookie(application)
    return application


def _facade(request: Request) -> GoldenPathFacade:
    facade = request.app.state.facade
    if not isinstance(facade, GoldenPathFacade):
        raise ApplicationError("internal", "closed")
    return facade


def _intent_id(raw: str) -> IntentId:
    try:
        return IntentId(raw)
    except DomainInvariantError as exc:
        raise ApplicationError(exc.field, exc.code) from None


def _closed_domain(exc: DomainInvariantError) -> ApplicationError:
    return ApplicationError(exc.field, exc.code)


def _intake_records(request: Request) -> dict[str, dict[str, str]]:
    store = getattr(request.app.state, "intake_records", None)
    if not isinstance(store, dict):
        store = {}
        request.app.state.intake_records = store
    return store


def register_agent_intake(application: FastAPI, correlation_id: str) -> str:
    """Mint an intake record so a prepared agent handoff can skip NL extraction."""

    intake_id = mint_opaque("in_")
    store = getattr(application.state, "intake_records", None)
    if not isinstance(store, dict):
        store = {}
        application.state.intake_records = store
    store[intake_id] = {"correlationId": correlation_id or mint_opaque("cr_")}
    return intake_id


def _competition_intents(request: Request) -> dict[str, dict[str, str]]:
    store = getattr(request.app.state, "competition_intents", None)
    if not isinstance(store, dict):
        store = {}
        request.app.state.competition_intents = store
    return store


def _require_owned(request: Request, intent_id: str) -> tuple[IntentId, dict[str, str]]:
    portfolio = portfolio_id_from(request)
    try:
        typed = IntentId(intent_id)
    except DomainInvariantError:
        raise ApplicationError("intentId", "unknown_resource") from None
    _facade(request).get_owned_snapshot(typed, portfolio)
    record = _competition_intents(request).get(intent_id)
    if record is None or record.get("portfolioId") != portfolio:
        raise ApplicationError("intentId", "unknown_resource")
    return typed, record


def _extract_client(request: Request) -> ExtractClient:
    client = getattr(request.app.state, "extract_client", None)
    if callable(client):
        return cast(ExtractClient, client)
    return http_extract_client


def http_extract_client(payload: dict[str, object]) -> dict[str, object]:
    base = os.environ.get("ITAA_GOOGLE_ADAPTER_URL", _DEFAULT_ADAPTER).rstrip("/")
    request = urllib.request.Request(
        f"{base}{_EXTRACT_PATH}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_EXTRACT_HTTP_TIMEOUT_S) as response:
            parsed = json.loads(response.read().decode("utf-8"))
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        json.JSONDecodeError,
        OSError,
    ):
        raise ApplicationError("model", "unavailable") from None
    if not isinstance(parsed, dict):
        raise ApplicationError("model", "unavailable")
    return parsed


def _call_extract(client: ExtractClient, payload: dict[str, object]) -> dict[str, object]:
    try:
        result = client(payload)
    except ApplicationError:
        raise
    except Exception:
        raise ApplicationError("model", "unavailable") from None
    if not isinstance(result, Mapping):
        raise ApplicationError("model", "unavailable")
    return dict(result)


def _disclosure_hash(
    *,
    airport_code: str,
    start: str,
    end: str,
    vehicle_class: str,
    covered: str,
    shuttle_max_minutes: int,
    currency: str,
    accessibility: list[str],
) -> str:
    material = {
        "accessibility": accessibility,
        "airportCode": airport_code,
        "covered": covered,
        "currency": currency,
        "end": end,
        "shuttleMaxMinutes": shuttle_max_minutes,
        "start": start,
        "vehicleClass": vehicle_class,
    }
    digest = hashlib.sha256(
        json.dumps(material, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    return f"sha256:{digest}"


def _intent_instants(request: Request) -> tuple[datetime, datetime, datetime]:
    created = _facade(request).now()
    return created, created + INTENT_TTL, created + SOLICITATION_TTL


def _mint_governance(
    request: Request,
    record: Mapping[str, str],
    *,
    expires_at: datetime | None = None,
) -> GovernanceCommand:
    issued_at, default_expires, _solicitation = _intent_instants(request)
    return GovernanceCommand(
        actor_id=record["actorId"],
        owner_id=record["ownerId"],
        approval_id=mint_opaque("ap_"),
        correlation_id=mint_opaque("cr_"),
        issued_at=issued_at,
        expires_at=expires_at or default_expires,
    )


def _offer_version(snapshot: BuyerSnapshot, offer_id: str, provided: int | None) -> int:
    if provided is not None:
        return provided
    for item in snapshot.offers:
        if item.offer_id == offer_id:
            return item.version
    raise ApplicationError("offerId", "unknown_resource")


def _fill_authorization(
    snapshot: BuyerSnapshot,
    body: IntakeAuthorizationBody,
) -> tuple[str, int, str, str, str, str]:
    acceptance = snapshot.acceptance
    if acceptance is None:
        raise ApplicationError("acceptanceId", "required")
    offer = next((item for item in snapshot.offers if item.offer_id == acceptance.offer_id), None)
    if offer is None:
        raise ApplicationError("offerId", "unknown_resource")
    return (
        body.acceptanceId or acceptance.acceptance_id,
        offer.total_minor if body.amountMinor is None else body.amountMinor,
        body.currency or offer.currency,
        body.supplierToken or offer.supplier_token,
        body.action or "reserve_parking",
        body.mode or "SIMULATED",
    )


@router.post(
    f"{PREFIX}/intake/extractions",
    tags=[OPENAPI_TAG],
    summary="Extract a parking requirement without persisting raw text",
)
def create_extraction(
    request: Request,
    body: Annotated[ExtractionBody, Body()],
) -> dict[str, object]:
    intake_id = mint_opaque("in_")
    correlation_id = mint_opaque("cr_")
    adapter = _call_extract(
        _extract_client(request),
        {
            "text": body.text,
            "category": body.category,
            "correlationId": correlation_id,
        },
    )
    _intake_records(request)[intake_id] = {"correlationId": correlation_id}
    adapter["intakeId"] = intake_id
    adapter.setdefault("correlationId", correlation_id)
    return adapter


@router.post(
    f"{PREFIX}/intake/intents",
    tags=[OPENAPI_TAG],
    summary="Create a competition PurchaseIntent from confirmed fields only",
)
def create_confirmed_intent(
    request: Request,
    body: Annotated[ConfirmedIntentBody, Body()],
) -> dict[str, object]:
    record = _intake_records(request).get(body.intakeId)
    if record is None:
        raise ApplicationError("intakeId", "unknown_resource")
    try:
        start = parse_utc(body.start, "start")
        end = parse_utc(body.end, "end")
        TimeWindow(start, end)
    except DomainInvariantError as exc:
        raise _closed_domain(exc) from None
    created, expires, solicitation = _intent_instants(request)
    payload = {
        "schemaVersion": "1.0",
        "intentId": mint_opaque("pi_"),
        "buyerToken": mint_opaque("bs_"),
        "category": "airport_parking",
        "location": {"airportCode": body.airportCode},
        "serviceWindow": {"start": body.start, "end": body.end},
        "requirements": {
            "vehicleClass": body.vehicleClass,
            "covered": body.covered,
            "shuttleMaxMinutes": body.shuttleMaxMinutes,
        },
        "constraints": {
            "currency": body.currency,
            "accessibility": list(body.accessibility),
        },
        "disclosure": {
            "profile": "parking_v1",
            "approvedPayloadHash": _disclosure_hash(
                airport_code=body.airportCode,
                start=body.start,
                end=body.end,
                vehicle_class=body.vehicleClass,
                covered=body.covered,
                shuttle_max_minutes=body.shuttleMaxMinutes,
                currency=body.currency,
                accessibility=list(body.accessibility),
            ),
        },
        "solicitation": {
            "responseDeadline": format_utc(solicitation),
            "counteroffersAllowed": True,
        },
        "createdAt": format_utc(created),
        "expiresAt": format_utc(expires),
    }
    snapshot = _facade(request).create_purchase_intent(
        payload, portfolio_id=portfolio_id_from(request)
    )
    actor = mint_opaque("ar_")
    _competition_intents(request)[snapshot.intent_id] = {
        "actorId": actor,
        "ownerId": actor,
        "portfolioId": portfolio_id_from(request),
    }
    return snapshot.to_primitive()


def create_owned_parking_intent(
    request: Request, fields: Mapping[str, object]
) -> dict[str, object]:
    """Mint a parking PI from canonical fields. Does not confirm A1 or dispatch."""

    intake_id = register_agent_intake(request.app, mint_opaque("cr_"))
    access = fields.get("accessibility")
    body = ConfirmedIntentBody.model_validate(
        {
            "intakeId": intake_id,
            "airportCode": fields["airportCode"],
            "start": fields["start"],
            "end": fields["end"],
            "vehicleClass": fields["vehicleClass"],
            "covered": fields["covered"],
            "shuttleMaxMinutes": fields["shuttleMaxMinutes"],
            "currency": fields["currency"],
            "accessibility": list(access) if isinstance(access, list) else [],
        }
    )
    return create_confirmed_intent(request, body)


@router.post(
    f"{PREFIX}/intake/intents/{{intent_id}}/confirm",
    tags=[OPENAPI_TAG],
    summary="A1 requirement confirmation with server-minted governance",
)
def confirm_intake_intent(
    request: Request,
    intent_id: str,
    body: Annotated[IntakeGateBody, Body()] = _EMPTY_GATE,
) -> dict[str, object]:
    del body
    typed, record = _require_owned(request, intent_id)
    return (
        _facade(request)
        .confirm_requirement(typed, _mint_governance(request, record))
        .to_primitive()
    )


@router.post(
    f"{PREFIX}/intake/intents/{{intent_id}}/dispatch",
    tags=[OPENAPI_TAG],
    summary="A2 dispatch with server-minted governance",
)
def dispatch_intake_intent(
    request: Request,
    intent_id: str,
    body: Annotated[IntakeGateBody, Body()] = _EMPTY_GATE,
) -> dict[str, object]:
    del body
    typed, record = _require_owned(request, intent_id)
    facade = _facade(request)
    snapshot = facade.get_owned_snapshot(typed, portfolio_id_from(request))
    governance = _mint_governance(
        request, record, expires_at=parse_utc(snapshot.expires_at, "expiresAt")
    )
    return facade.approve_and_dispatch(typed, governance).to_primitive()


@router.post(
    f"{PREFIX}/intake/intents/{{intent_id}}/acceptances",
    tags=[OPENAPI_TAG],
    summary="A3 acceptance with server-minted governance",
)
def accept_intake_intent(
    request: Request,
    intent_id: str,
    body: Annotated[IntakeAcceptanceBody, Body()],
) -> dict[str, object]:
    typed, record = _require_owned(request, intent_id)
    facade = _facade(request)
    snapshot = facade.get_owned_snapshot(typed, portfolio_id_from(request))
    version = _offer_version(snapshot, body.offerId, body.offerVersion)
    governance = _mint_governance(request, record)
    command = AcceptCommand(
        actor_id=governance.actor_id,
        owner_id=governance.owner_id,
        approval_id=governance.approval_id,
        correlation_id=governance.correlation_id,
        issued_at=governance.issued_at,
        expires_at=governance.expires_at,
        offer_id=body.offerId,
        offer_version=version,
    )
    return facade.accept_recommended_or_selected_offer(typed, command).to_primitive()


@router.post(
    f"{PREFIX}/intake/intents/{{intent_id}}/transaction-authorizations",
    tags=[OPENAPI_TAG],
    summary="A4 simulated authorization with server-minted governance",
)
def authorize_intake_intent(
    request: Request,
    intent_id: str,
    body: Annotated[IntakeAuthorizationBody, Body()] = _EMPTY_AUTHORIZATION,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, object]:
    typed, record = _require_owned(request, intent_id)
    facade = _facade(request)
    snapshot = facade.get_owned_snapshot(typed, portfolio_id_from(request))
    acceptance_id, amount_minor, currency, supplier_token, action, mode = _fill_authorization(
        snapshot, body
    )
    stored_key = record.get("idempotencyKey")
    key = idempotency_key or stored_key or mint_opaque("ik_")
    if (
        not key.startswith("ik_")
        or len(key) != 29
        or any(char not in _CROCKFORD for char in key[3:])
    ):
        raise ApplicationError("idempotencyKey", "schema_invalid")
    record["idempotencyKey"] = key
    governance = _mint_governance(request, record)
    command = AuthorizeCommand(
        actor_id=governance.actor_id,
        owner_id=governance.owner_id,
        approval_id=governance.approval_id,
        correlation_id=governance.correlation_id,
        issued_at=governance.issued_at,
        expires_at=governance.expires_at,
        acceptance_id=acceptance_id,
        amount_minor=amount_minor,
        currency=currency,
        supplier_token=supplier_token,
        action=action,
        mode=mode,
        idempotency_key=key,
    )
    return facade.authorize_simulated_transaction(typed, command).to_primitive()


def _bind_draft(request: Request, intent_id: str, portfolio_id: str) -> None:
    actor = mint_opaque("ar_")
    _competition_intents(request)[intent_id] = {
        "actorId": actor,
        "ownerId": actor,
        "portfolioId": portfolio_id,
    }


@router.get(
    f"{PREFIX}/intake/intents",
    tags=[OPENAPI_TAG],
    summary="List this browser's simulated parking requests",
)
def list_intake_intents(request: Request) -> dict[str, object]:
    snapshots = _facade(request).list_buyer_snapshots(portfolio_id_from(request))
    return cast(dict[str, object], bucket_snapshots(snapshots))


@router.get(
    f"{PREFIX}/intake/intents/{{intent_id}}",
    tags=[OPENAPI_TAG],
    summary="Read one owned simulated parking request",
)
def get_intake_intent(request: Request, intent_id: str) -> dict[str, object]:
    typed, _record = _require_owned(request, intent_id)
    return _facade(request).get_owned_snapshot(typed, portfolio_id_from(request)).to_primitive()


@router.post(
    f"{PREFIX}/intake/intents/{{intent_id}}/cancel",
    tags=[OPENAPI_TAG],
    summary="Cancel an owned request before simulated authorization",
)
def cancel_intake_intent(
    request: Request,
    intent_id: str,
    body: Annotated[IntakeGateBody, Body()] = _EMPTY_GATE,
) -> dict[str, object]:
    del body
    typed, record = _require_owned(request, intent_id)
    return (
        _facade(request)
        .cancel_purchase_intent(
            typed, portfolio_id_from(request), _mint_governance(request, record)
        )
        .to_primitive()
    )


@router.post(
    f"{PREFIX}/intake/intents/{{intent_id}}/replace",
    tags=[OPENAPI_TAG],
    summary="Start a revised request from an owned original",
)
def replace_intake_intent(
    request: Request,
    intent_id: str,
    body: Annotated[IntakeGateBody, Body()] = _EMPTY_GATE,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, object]:
    del body
    if idempotency_key is None:
        raise ApplicationError("idempotencyKey", "schema_invalid")
    key = require_idempotency_key(idempotency_key)
    typed, record = _require_owned(request, intent_id)
    portfolio = portfolio_id_from(request)
    result = _facade(request).replace_purchase_intent(
        typed, portfolio, _mint_governance(request, record), key
    )
    if result.draft.intent_id not in _competition_intents(request):
        _bind_draft(request, result.draft.intent_id, portfolio)
    return result.to_primitive()


@router.delete(
    f"{PREFIX}/intake/intents/{{intent_id}}",
    tags=[OPENAPI_TAG],
    summary="Delete an undisclosed draft owned by this browser",
)
def delete_intake_intent(request: Request, intent_id: str) -> dict[str, object]:
    typed, _record = _require_owned(request, intent_id)
    _facade(request).delete_undisclosed_draft(typed, portfolio_id_from(request))
    _competition_intents(request).pop(intent_id, None)
    return {"deleted": True}


@router.post(
    f"{PREFIX}/intake/intents/{{intent_id}}/save",
    tags=[OPENAPI_TAG],
    summary="Save an owned request for later without changing domain state",
)
def save_intake_intent(
    request: Request,
    intent_id: str,
    body: Annotated[IntakeGateBody, Body()] = _EMPTY_GATE,
) -> dict[str, object]:
    del body
    typed, _record = _require_owned(request, intent_id)
    return _facade(request).set_saved(typed, portfolio_id_from(request), True).to_primitive()


@router.delete(
    f"{PREFIX}/intake/intents/{{intent_id}}/save",
    tags=[OPENAPI_TAG],
    summary="Remove save-for-later from an owned request",
)
def unsave_intake_intent(request: Request, intent_id: str) -> dict[str, object]:
    typed, _record = _require_owned(request, intent_id)
    return _facade(request).set_saved(typed, portfolio_id_from(request), False).to_primitive()


@router.get(
    f"{PREFIX}/intake/intents/{{intent_id}}/activity",
    tags=[OPENAPI_TAG],
    summary="Human-language activity for an owned request",
)
def intake_intent_activity(request: Request, intent_id: str) -> dict[str, object]:
    typed, _record = _require_owned(request, intent_id)
    entries = _facade(request).buyer_activity(typed, portfolio_id_from(request))
    return {"activity": list(entries)}
