"""Orchestration read routes. In-memory only; restart yields unknown_resource."""

from __future__ import annotations

from fastapi import APIRouter, Request

from itaa_api.schemas import (
    BookingTask,
    CostLedger,
    ErrorEnvelope,
    IntentPlan,
    OrchestrationIntent,
)
from itaa_application.errors import ApplicationError
from itaa_application.orchestration import OrchestrationService

PREFIX = "/v1/orchestration"
OPENAPI_TAG = "orchestration"
_RESTART = (
    "In-memory only. Durability is unsupported. Restart discards process state "
    "and yields unknown_resource."
)

router = APIRouter()


def _service(request: Request) -> OrchestrationService:
    service = getattr(request.app.state, "orchestration", None)
    if not isinstance(service, OrchestrationService):
        raise ApplicationError("internal", "closed")
    return service


@router.get(
    f"{PREFIX}/intents/{{id}}",
    response_model=OrchestrationIntent,
    response_model_exclude_none=True,
    responses={
        400: {"model": ErrorEnvelope},
        404: {"model": ErrorEnvelope},
    },
    tags=[OPENAPI_TAG],
    summary="Read an orchestration Intent",
    description=(
        "Returns the buyer-owned parent Intent. Accepts canonical oi_* or the "
        f"pi_* purchase-intent alias. {_RESTART}"
    ),
)
def get_orchestration_intent(request: Request, id: str) -> dict[str, object]:
    return _service(request).get_intent(id)


@router.get(
    f"{PREFIX}/intents/{{id}}/plan",
    response_model=IntentPlan,
    response_model_exclude_none=True,
    responses={
        400: {"model": ErrorEnvelope},
        404: {"model": ErrorEnvelope},
    },
    tags=[OPENAPI_TAG],
    summary="Read the Intent plan",
    description=f"Returns the IntentPlan for the parent Intent. {_RESTART}",
)
def get_orchestration_plan(request: Request, id: str) -> dict[str, object]:
    return _service(request).get_plan(id)


@router.get(
    f"{PREFIX}/intents/{{id}}/ledger",
    response_model=CostLedger,
    response_model_exclude_none=True,
    responses={
        400: {"model": ErrorEnvelope},
        404: {"model": ErrorEnvelope},
    },
    tags=[OPENAPI_TAG],
    summary="Read the cost ledger",
    description=f"Returns the CostLedger for the parent Intent. {_RESTART}",
)
def get_orchestration_ledger(request: Request, id: str) -> dict[str, object]:
    return _service(request).get_ledger(id)


@router.get(
    f"{PREFIX}/intents/{{id}}/tasks/{{task_id}}",
    response_model=BookingTask,
    response_model_exclude_none=True,
    responses={
        400: {"model": ErrorEnvelope},
        404: {"model": ErrorEnvelope},
    },
    tags=[OPENAPI_TAG],
    summary="Read a Booking Task",
    description=(
        f"Returns one Booking Task. The task must belong to the parent Intent. {_RESTART}"
    ),
)
def get_orchestration_task(request: Request, id: str, task_id: str) -> dict[str, object]:
    return _service(request).get_task(id, task_id)
