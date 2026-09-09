"""FastAPI wrapper around the cloud-neutral local API plus Google adapter routes.

CORS defaults to local Vite. Cloudflare Pages origin is documented as
``https://app.example.invalid`` — set it via ``ITAA_CORS_ORIGINS``. No Workers
product and no Vercel.
"""

from __future__ import annotations

import os
from typing import Annotated, Any

from fastapi import APIRouter, Body, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from itaa_api.app import create_app
from itaa_application.errors import ApplicationError
from itaa_application.golden_path import GoldenPathFacade
from itaa_google_adapter.agent import GoogleAdapterAgent, compose_agent
from itaa_google_adapter.extraction import attribution_to_http
from itaa_google_adapter.mode import MODE_FAKE, MODE_LIVE, peek_model_mode
from itaa_google_adapter.ports import (
    ExplanationRequest,
    ExtractionRequest,
    RankingFacts,
    SafeOfferSummary,
)

DEFAULT_CORS_ORIGIN = "http://localhost:5173"
CLOUDFLARE_PAGES_PLACEHOLDER = "https://app.example.invalid"
GOOGLE_PREFIX = "/v1/google"

google_router = APIRouter()


class ExtractionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    category: str
    correlationId: str = Field(pattern="^cr_[0-9a-hjkmnp-tv-z]{26}$")


class OfferFactBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supplierToken: str = Field(pattern="^sp_[0-9a-hjkmnp-tv-z]{26}$")
    displayName: str
    offerId: str = Field(pattern="^of_[0-9a-hjkmnp-tv-z]{26}$")
    rank: int = Field(ge=1)
    scoreMicros: int
    totalMinor: int
    currency: str = Field(pattern="^[A-Z]{3}$")
    recommended: bool


class DownsideBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dimension: str
    delta: int
    versusOfferId: str | None = None


class ExplanationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    correlationId: str = Field(pattern="^cr_[0-9a-hjkmnp-tv-z]{26}$")
    recommendedOfferId: str = Field(pattern="^of_[0-9a-hjkmnp-tv-z]{26}$")
    winnerDisplayName: str
    offers: list[OfferFactBody]
    downside: DownsideBody


def documented_cors_origins() -> tuple[str, ...]:
    return (DEFAULT_CORS_ORIGIN, CLOUDFLARE_PAGES_PLACEHOLDER)


def cors_origins_from_env(raw: str | None = None) -> list[str]:
    text = DEFAULT_CORS_ORIGIN if raw is None else raw
    if raw is None:
        text = os.environ.get("ITAA_CORS_ORIGINS", DEFAULT_CORS_ORIGIN)
    origins = [item.strip() for item in text.split(",") if item.strip()]
    return origins or [DEFAULT_CORS_ORIGIN]


def _agent(request: Request) -> GoogleAdapterAgent:
    agent = getattr(request.app.state, "google_agent", None)
    if not isinstance(agent, GoogleAdapterAgent):
        raise ApplicationError("model", "schema_invalid")
    return agent


@google_router.post(f"{GOOGLE_PREFIX}/extractions")
def create_extraction(
    request: Request,
    body: Annotated[ExtractionBody, Body()],
) -> dict[str, Any]:
    result = _agent(request).extract(
        ExtractionRequest(
            text=body.text,
            category=body.category,
            correlation_id=body.correlationId,
        )
    )
    return {
        "proposal": None if result.proposal is None else dict(result.proposal),
        "fieldConfidence": dict(result.field_confidence),
        "missingFields": list(result.missing_fields),
        "ambiguousFields": list(result.ambiguous_fields),
        "evidenceSpans": [
            {"field": item.field, "start": item.start, "end": item.end}
            for item in result.evidence_spans
        ],
        "fieldAttributions": [attribution_to_http(item) for item in result.field_attributions],
        "requiresA1": True,
        "accepted": False,
        "fallback": result.fallback,
        "rejectionCode": result.rejection_code,
        "correlationId": body.correlationId,
    }


@google_router.post(f"{GOOGLE_PREFIX}/explanations")
def create_explanation(
    request: Request,
    body: Annotated[ExplanationBody, Body()],
) -> dict[str, Any]:
    facts = RankingFacts(
        winner_id=body.recommendedOfferId,
        winner_display_name=body.winnerDisplayName,
        offers=tuple(
            SafeOfferSummary(
                supplier_token=item.supplierToken,
                display_name=item.displayName,
                offer_id=item.offerId,
                rank=item.rank,
                score_micros=item.scoreMicros,
                total_minor=item.totalMinor,
                currency=item.currency,
                recommended=item.recommended,
            )
            for item in body.offers
        ),
        downside_delta=body.downside.delta,
        downside_dimension=body.downside.dimension,
        correlation_id=body.correlationId,
    )
    result = _agent(request).explain(ExplanationRequest(facts=facts))
    return {
        "explanation": result.explanation,
        "grounded": result.grounded,
        "fallback": result.fallback,
        "correlationId": body.correlationId,
    }


def google_readyz() -> JSONResponse:
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
        from itaa_google_adapter.live import live_runtime_ready

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
    application.add_api_route("/readyz", google_readyz, methods=["GET"])


def create_google_app(facade: GoldenPathFacade | None = None) -> FastAPI:
    inner = create_app(facade)
    try:
        inner.state.google_agent = compose_agent(facade=inner.state.facade)
    except ApplicationError:
        inner.state.google_agent = None
    inner.include_router(google_router)
    _override_readyz(inner)
    inner.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins_from_env(),
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["authorization", "content-type", "x-correlation-id"],
        allow_credentials=False,
    )
    return inner


app = create_google_app()
