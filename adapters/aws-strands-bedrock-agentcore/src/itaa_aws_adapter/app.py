"""FastAPI wrapper around the cloud-neutral local API plus AWS adapter routes.

Browser product path is /v1/agent/** (COMP-AWS-02). This module exposes /v1/aws/**
only. Combined process must not HTTP-loopback into /v1/agent/**.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Annotated, Any

from fastapi import APIRouter, Body, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from itaa_api.app import create_app
from itaa_api.composition import build_facade
from itaa_application.errors import ApplicationError
from itaa_application.golden_path import GoldenPathFacade
from itaa_application.supplier_port import WallClock
from itaa_aws_adapter.agent import BuyerOrchestrator, compose_orchestrator
from itaa_aws_adapter.mode import MODE_FAKE, MODE_LIVE, peek_model_mode
from itaa_aws_adapter.schemas import PlanAnswers, PlanTurnContext

DEFAULT_CORS_ORIGIN = "http://localhost:5173"
CLOUDFLARE_PAGES_PLACEHOLDER = "https://app.example.invalid"
AWS_PREFIX = "/v1/aws"

aws_router = APIRouter()


class PlanTurnBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    objective: str
    answers: PlanAnswers | None = None
    correlationId: str | None = Field(default=None, pattern="^cr_[0-9a-hjkmnp-tv-z]{26}$")
    lastUserMessage: str = ""
    trustedDomains: dict[str, Any] = Field(default_factory=dict)


class ExecuteTurnBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: str
    payload: dict[str, Any] = Field(default_factory=dict)
    correlationId: str | None = Field(default=None, pattern="^cr_[0-9a-hjkmnp-tv-z]{26}$")


def documented_cors_origins() -> tuple[str, ...]:
    return (DEFAULT_CORS_ORIGIN, CLOUDFLARE_PAGES_PLACEHOLDER)


def cors_origins_from_env(raw: str | None = None) -> list[str]:
    text = DEFAULT_CORS_ORIGIN if raw is None else raw
    if raw is None:
        text = os.environ.get("ITAA_CORS_ORIGINS", DEFAULT_CORS_ORIGIN)
    origins = [item.strip() for item in text.split(",") if item.strip()]
    return origins or [DEFAULT_CORS_ORIGIN]


class InProcessAwsProvider:
    """Same-process Plan/Execute. Never HTTP-loopback into this worker."""

    def __init__(
        self,
        orchestrator: BuyerOrchestrator | None,
        closed: ApplicationError | None = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._closed = closed

    def _require(self) -> BuyerOrchestrator:
        if self._orchestrator is None:
            raise self._closed or ApplicationError("model", "unavailable")
        return self._orchestrator

    def plan_turn(self, payload: Mapping[str, object]) -> dict[str, object]:
        orchestrator = self._require()
        raw_answers = payload.get("answers")
        answers = PlanAnswers.model_validate(raw_answers if isinstance(raw_answers, dict) else {})
        objective = str(payload.get("objective") or "")
        raw_trusted = payload.get("trustedDomains")
        context = PlanTurnContext(
            lastUserMessage=str(payload.get("lastUserMessage") or ""),
            trustedDomains=raw_trusted if isinstance(raw_trusted, dict) else {},
        )
        model, projection, events = orchestrator.plan_turn(objective, answers, context)
        return {
            "planTurn": model.model_dump(mode="json"),
            "projection": projection.model_dump(mode="json"),
            "events": events,
            "correlationId": payload.get("correlationId"),
        }

    def execute_turn(self, payload: Mapping[str, object]) -> dict[str, object]:
        orchestrator = self._require()
        tool = str(payload.get("tool") or "")
        inner = payload.get("payload")
        result = orchestrator.execute_turn(tool, inner if isinstance(inner, dict) else {})
        return {
            "tool": tool,
            "result": result,
            "correlationId": payload.get("correlationId"),
        }


def _orchestrator(request: Request) -> BuyerOrchestrator:
    agent = getattr(request.app.state, "aws_orchestrator", None)
    if not isinstance(agent, BuyerOrchestrator):
        raise ApplicationError("model", "schema_invalid")
    return agent


@aws_router.post(f"{AWS_PREFIX}/plan-turns")
def create_plan_turn(
    request: Request,
    body: Annotated[PlanTurnBody, Body()],
) -> dict[str, Any]:
    orchestrator = _orchestrator(request)
    model, projection, events = orchestrator.plan_turn(
        body.objective,
        body.answers,
        PlanTurnContext(lastUserMessage=body.lastUserMessage, trustedDomains=body.trustedDomains),
    )
    return {
        "planTurn": model.model_dump(mode="json"),
        "projection": projection.model_dump(mode="json"),
        "events": events,
        "correlationId": body.correlationId,
    }


@aws_router.post(f"{AWS_PREFIX}/execute-turns")
def create_execute_turn(
    request: Request,
    body: Annotated[ExecuteTurnBody, Body()],
) -> dict[str, Any]:
    orchestrator = _orchestrator(request)
    result = orchestrator.execute_turn(body.tool, body.payload)
    return {"tool": body.tool, "result": result, "correlationId": body.correlationId}


def aws_readyz() -> JSONResponse:
    mode = peek_model_mode()
    if mode not in {MODE_FAKE, MODE_LIVE}:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "adapter": "unknown",
                "environment": "local_simulation",
            },
        )
    if mode == MODE_LIVE:
        from itaa_aws_adapter.live import live_runtime_ready

        if not live_runtime_ready():
            return JSONResponse(
                status_code=503,
                content={
                    "status": "unavailable",
                    "adapter": "live",
                    "environment": "local_simulation",
                },
            )
    return JSONResponse(
        status_code=200,
        content={
            "status": "ready",
            "environment": "local_simulation",
            "durability": "unsupported",
        },
    )


def _override_readyz(application: FastAPI) -> None:
    application.router.routes = [
        route
        for route in application.router.routes
        if not (
            getattr(route, "path", None) == "/readyz" and "GET" in getattr(route, "methods", set())
        )
    ]
    application.add_api_route("/readyz", aws_readyz, methods=["GET"])


def create_aws_app(facade: GoldenPathFacade | None = None) -> FastAPI:
    inner = create_app(facade if facade is not None else build_facade(clock=WallClock()))
    closed: ApplicationError | None = None
    orchestrator: BuyerOrchestrator | None = None
    try:
        orchestrator = compose_orchestrator(facade=inner.state.facade)
    except ApplicationError as exc:
        closed = exc
    inner.state.aws_orchestrator = orchestrator
    inner.state.aws_provider = InProcessAwsProvider(orchestrator, closed)
    inner.include_router(aws_router)
    _override_readyz(inner)
    inner.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins_from_env(),
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["authorization", "content-type", "x-correlation-id"],
        allow_credentials=False,
    )
    return inner


app = create_aws_app()
