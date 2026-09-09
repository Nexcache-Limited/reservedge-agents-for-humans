"""Local simulation HTTP routes. Governance stays in the application facade."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Header, Request

from itaa_api.schemas import (
    AcceptanceBody,
    AuthorizationBody,
    BuyerSessionSnapshot,
    ErrorEnvelope,
    GovernanceBody,
    LivenessResponse,
    ReadinessResponse,
)
from itaa_application.errors import ApplicationError
from itaa_application.golden_path import GoldenPathFacade
from itaa_application.session_models import (
    AcceptCommand,
    AuthorizeCommand,
    GovernanceCommand,
)
from itaa_contracts_generated.purchase_intent import PurchaseIntent as ContractPurchaseIntent
from itaa_domain.errors import DomainInvariantError
from itaa_domain.identifiers import IntentId
from itaa_domain.value_objects import parse_utc

PREFIX = "/v1/simulations/airport-parking"
OPENAPI_TAG = "local-simulation"

router = APIRouter()


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


def _governance(body: GovernanceBody) -> GovernanceCommand:
    return GovernanceCommand(
        actor_id=body.actorId,
        owner_id=body.ownerId,
        approval_id=body.approvalId,
        correlation_id=body.correlationId,
        issued_at=parse_utc(body.issuedAt, "issuedAt"),
        expires_at=parse_utc(body.expiresAt, "expiresAt"),
    )


@router.get(
    "/healthz",
    response_model=LivenessResponse,
    responses={400: {"model": ErrorEnvelope}},
    tags=[OPENAPI_TAG],
    summary="Process liveness",
    description="Local simulation liveness only. No configuration, credentials, or session state.",
)
def healthz() -> LivenessResponse:
    return LivenessResponse(status="ok", environment="local_simulation")


@router.get(
    "/readyz",
    response_model=ReadinessResponse,
    responses={400: {"model": ErrorEnvelope}},
    tags=[OPENAPI_TAG],
    summary="Local composition readiness",
    description=(
        "Confirms the in-memory local composition is ready. "
        "Makes no external calls. Durability is unsupported."
    ),
)
def readyz() -> ReadinessResponse:
    return ReadinessResponse(
        status="ready",
        environment="local_simulation",
        durability="unsupported",
    )


@router.post(
    f"{PREFIX}/intents",
    responses={400: {"model": ErrorEnvelope}, 409: {"model": ErrorEnvelope}},
    tags=[OPENAPI_TAG],
    summary="Create a local simulated purchase-intent session",
    description=(
        "Accepts the canonical PurchaseIntent v1 representation. "
        "Local simulation only. HTTP is not production authorization."
    ),
)
def create_intent(
    request: Request,
    payload: Annotated[ContractPurchaseIntent, Body()],
) -> dict[str, object]:
    return _facade(request).create_purchase_intent(payload.model_dump(mode="json")).to_primitive()


@router.post(
    f"{PREFIX}/intents/{{intent_id}}/confirm",
    responses={
        400: {"model": ErrorEnvelope},
        404: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
    },
    tags=[OPENAPI_TAG],
    summary="A1 requirement confirmation",
    description=(
        "Records explicit A1 confirmation. Opaque identifiers are "
        "governance inputs, not authenticated identity."
    ),
)
def confirm_intent(request: Request, intent_id: str, body: GovernanceBody) -> dict[str, object]:
    return (
        _facade(request)
        .confirm_requirement(_intent_id(intent_id), _governance(body))
        .to_primitive()
    )


@router.post(
    f"{PREFIX}/intents/{{intent_id}}/dispatch",
    responses={
        400: {"model": ErrorEnvelope},
        404: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
    },
    tags=[OPENAPI_TAG],
    summary="A2 dispatch and isolated simulated solicitation",
    description=(
        "Requires exact A2 approval, then runs three isolated simulated "
        "suppliers. Offers and availability are simulated."
    ),
)
def dispatch_intent(request: Request, intent_id: str, body: GovernanceBody) -> dict[str, object]:
    return (
        _facade(request)
        .approve_and_dispatch(_intent_id(intent_id), _governance(body))
        .to_primitive()
    )


@router.get(
    f"{PREFIX}/intents/{{intent_id}}",
    responses={
        200: {"model": BuyerSessionSnapshot},
        404: {"model": ErrorEnvelope},
    },
    tags=[OPENAPI_TAG],
    summary="Buyer-safe session snapshot",
    description=(
        "Returns a minimized local-simulation snapshot. No raw context, "
        "prompts, audit payloads, or supplier policy internals."
    ),
)
def get_intent(request: Request, intent_id: str) -> dict[str, object]:
    return _facade(request).get_buyer_snapshot(_intent_id(intent_id)).to_primitive()


@router.post(
    f"{PREFIX}/intents/{{intent_id}}/acceptances",
    responses={
        400: {"model": ErrorEnvelope},
        404: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
    },
    tags=[OPENAPI_TAG],
    summary="A3 offer acceptance",
    description=(
        "Accepts the recommendation or another eligible simulated offer "
        "after exact A3 approval. No real reservation."
    ),
)
def accept_intent(request: Request, intent_id: str, body: AcceptanceBody) -> dict[str, object]:
    command = AcceptCommand(
        actor_id=body.actorId,
        owner_id=body.ownerId,
        approval_id=body.approvalId,
        correlation_id=body.correlationId,
        issued_at=parse_utc(body.issuedAt, "issuedAt"),
        expires_at=parse_utc(body.expiresAt, "expiresAt"),
        offer_id=body.offerId,
        offer_version=body.offerVersion,
    )
    return (
        _facade(request)
        .accept_recommended_or_selected_offer(_intent_id(intent_id), command)
        .to_primitive()
    )


@router.post(
    f"{PREFIX}/intents/{{intent_id}}/transaction-authorizations",
    responses={
        400: {"model": ErrorEnvelope},
        404: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
    },
    tags=[OPENAPI_TAG],
    summary="A4 SIMULATED transaction authorization",
    description=(
        "Produces only a SIMULATED reserve_parking authorization. "
        "Never performs payment or a live reservation. "
        "Requires the Idempotency-Key header and body idempotencyKey to be present "
        "and equal. Missing or mismatched values are rejected with a closed error. "
        "Exact replay of the same header, body key, and request returns the same "
        "result reference."
    ),
)
def authorize_intent(
    request: Request,
    intent_id: str,
    body: AuthorizationBody,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description=(
                "Required. Must equal the JSON body field idempotencyKey. "
                "Missing or mismatched values are rejected with a closed error "
                "that does not echo either value."
            ),
        ),
    ],
) -> dict[str, object]:
    if idempotency_key != body.idempotencyKey:
        raise ApplicationError("idempotencyKey", "mismatch")
    command = AuthorizeCommand(
        actor_id=body.actorId,
        owner_id=body.ownerId,
        approval_id=body.approvalId,
        correlation_id=body.correlationId,
        issued_at=parse_utc(body.issuedAt, "issuedAt"),
        expires_at=parse_utc(body.expiresAt, "expiresAt"),
        acceptance_id=body.acceptanceId,
        amount_minor=body.amountMinor,
        currency=body.currency,
        supplier_token=body.supplierToken,
        action=body.action,
        mode=body.mode,
        idempotency_key=body.idempotencyKey,
    )
    return (
        _facade(request)
        .authorize_simulated_transaction(_intent_id(intent_id), command)
        .to_primitive()
    )
