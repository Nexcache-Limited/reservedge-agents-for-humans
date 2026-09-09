"""Same-origin portfolio cookie and buyer list bucketing. No identity fields."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from itaa_application.errors import ApplicationError
from itaa_application.portfolio import mint_portfolio_id, require_portfolio_id
from itaa_application.session_models import BuyerSessionState, BuyerSnapshot

COOKIE_NAME = "itaa_portfolio"
_HISTORY = frozenset(
    {
        BuyerSessionState.CANCELLED,
        BuyerSessionState.SUPERSEDED,
        BuyerSessionState.TRANSACTION_AUTHORIZED_SIMULATED,
    }
)
_NEEDS = frozenset(
    {
        BuyerSessionState.AWAITING_REQUIREMENT_CONFIRMATION,
        BuyerSessionState.AWAITING_DISPATCH_APPROVAL,
        BuyerSessionState.OFFERS_RANKED,
        BuyerSessionState.ACCEPTANCE_RECORDED,
    }
)


class PortfolioCookieMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        raw = request.cookies.get(COOKIE_NAME)
        minted = False
        try:
            portfolio = require_portfolio_id(raw) if raw else mint_portfolio_id()
            minted = raw != portfolio
        except ApplicationError:
            portfolio = mint_portfolio_id()
            minted = True
        request.state.portfolio_id = portfolio
        response = await call_next(request)
        if minted:
            response.set_cookie(
                COOKIE_NAME,
                portfolio,
                httponly=True,
                samesite="lax",
                path="/",
                secure=False,
            )
        return response


def portfolio_id_from(request: Request) -> str:
    raw = getattr(request.state, "portfolio_id", None)
    if not isinstance(raw, str):
        raise ApplicationError("portfolio", "unknown_resource")
    return require_portfolio_id(raw)


def bucket_snapshots(snapshots: tuple[BuyerSnapshot, ...]) -> dict[str, list[dict[str, object]]]:
    needs: list[dict[str, object]] = []
    running: list[dict[str, object]] = []
    saved: list[dict[str, object]] = []
    history: list[dict[str, object]] = []
    for item in snapshots:
        row = item.to_primitive()
        if item.state in _HISTORY:
            history.append(row)
        elif item.saved:
            saved.append(row)
        elif item.state in _NEEDS:
            needs.append(row)
        else:
            running.append(row)
    needs.sort(key=_updated_key, reverse=True)
    running.sort(key=_updated_key, reverse=True)
    saved.sort(key=_saved_key, reverse=True)
    history.sort(key=_updated_key, reverse=True)
    return {"needsYou": needs, "running": running, "saved": saved, "history": history}


def _updated_key(row: dict[str, object]) -> tuple[str, str, str]:
    return (
        str(row.get("updatedAt", "")),
        str(row.get("airport", "")),
        str(row.get("createdAt", "")),
    )


def _saved_key(row: dict[str, object]) -> tuple[str, str, str]:
    return (
        str(row.get("savedAt") or ""),
        str(row.get("updatedAt", "")),
        str(row.get("airport", "")),
    )


def attach_portfolio_cookie(application: object) -> None:
    add = getattr(application, "add_middleware", None)
    if callable(add):
        add(PortfolioCookieMiddleware)
