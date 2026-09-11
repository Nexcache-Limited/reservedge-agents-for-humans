"""Local FastAPI application. HTTP is not production authorization."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from itaa_api.agent_session import attach_default_plan_provider
from itaa_api.agent_session import router as agent_router
from itaa_api.composition import build_facade
from itaa_api.errors import (
    application_error_handler,
    http_exception_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from itaa_api.intake import router as intake_router
from itaa_api.orchestration_routes import router as orchestration_router
from itaa_api.portfolio_http import attach_portfolio_cookie
from itaa_api.progress_sse import router as progress_router
from itaa_api.routes import router
from itaa_application.errors import ApplicationError
from itaa_application.golden_path import GoldenPathFacade
from itaa_application.local_progress import InMemoryProgressBus
from itaa_application.orchestration import OrchestrationService
from itaa_application.progress_events import ProgressSink

OPENAPI_DESCRIPTION = (
    "ITAA local simulation API v1. This surface is a process-local airport-parking "
    "golden path. It does not implement production authentication. It never places a "
    "real reservation or payment. All offers and availability are simulated. "
    "In-memory state is lost on restart. Restart yields unknown_resource. "
    "Durability is unsupported. Durable persistence is WP-11. "
    "GET .../events is a process-local SSE progress stream with a bounded buffer; "
    "it is not a second domain state machine and is discarded on restart."
)


def create_app(
    facade: GoldenPathFacade | None = None,
    progress: ProgressSink | None = None,
) -> FastAPI:
    bus: InMemoryProgressBus
    if facade is None:
        bus = progress if isinstance(progress, InMemoryProgressBus) else InMemoryProgressBus()
        facade = build_facade(progress=bus)
    elif isinstance(progress, InMemoryProgressBus):
        bus = progress
    else:
        attached = getattr(facade, "_progress", None)
        bus = attached if isinstance(attached, InMemoryProgressBus) else InMemoryProgressBus()
    application = FastAPI(
        title="ITAA Local Simulation API",
        version="1.0.0",
        description=OPENAPI_DESCRIPTION,
        docs_url=None,
        redoc_url=None,
    )
    application.state.facade = facade
    application.state.progress = bus
    application.state.orchestration = OrchestrationService(facade)
    application.include_router(router)
    application.include_router(progress_router)
    application.include_router(intake_router)
    application.include_router(orchestration_router)
    application.include_router(agent_router)
    attach_default_plan_provider(application)
    application.add_exception_handler(ApplicationError, application_error_handler)  # type: ignore[arg-type]
    application.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    application.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    application.add_exception_handler(Exception, unhandled_error_handler)
    attach_portfolio_cookie(application)
    return application


app = create_app()
