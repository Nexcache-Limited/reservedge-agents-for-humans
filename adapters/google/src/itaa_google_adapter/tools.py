"""Closed GoldenPathFacade wrappers. Tools never skip A1–A4 or live booking."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from itaa_application.errors import ApplicationError
from itaa_application.golden_path import GoldenPathFacade, map_closed_error
from itaa_application.session_models import (
    AcceptCommand,
    AuthorizeCommand,
    BuyerSnapshot,
    GovernanceCommand,
)
from itaa_domain.errors import DomainInvariantError
from itaa_domain.identifiers import (
    AcceptanceId,
    ApprovalId,
    CorrelationId,
    IdempotencyKey,
    IntentId,
    OfferId,
    SupplierToken,
)
from itaa_domain.value_objects import parse_utc

CLOSED_TOOLS: tuple[str, ...] = (
    "get_buyer_snapshot",
    "create_purchase_intent",
    "confirm_requirement",
    "approve_and_dispatch",
    "accept_offer",
    "authorize_simulated_transaction",
)


def _intent(raw: object) -> IntentId:
    try:
        return IntentId(str(raw))
    except DomainInvariantError as exc:
        raise ApplicationError(exc.field, exc.code) from None


def _correlation(raw: object) -> str:
    try:
        return CorrelationId(str(raw)).to_primitive()
    except DomainInvariantError as exc:
        raise ApplicationError(exc.field, exc.code) from None


def _approval(raw: object) -> str:
    try:
        return ApprovalId(str(raw)).to_primitive()
    except DomainInvariantError as exc:
        raise ApplicationError(exc.field, exc.code) from None


def _offer(raw: object) -> str:
    try:
        return OfferId(str(raw)).to_primitive()
    except DomainInvariantError as exc:
        raise ApplicationError(exc.field, exc.code) from None


def _supplier(raw: object) -> str:
    try:
        return SupplierToken(str(raw)).to_primitive()
    except DomainInvariantError as exc:
        raise ApplicationError(exc.field, exc.code) from None


def _acceptance(raw: object) -> str:
    try:
        return AcceptanceId(str(raw)).to_primitive()
    except DomainInvariantError as exc:
        raise ApplicationError(exc.field, exc.code) from None


def _idempotency(raw: object) -> str:
    try:
        return IdempotencyKey(str(raw)).to_primitive()
    except DomainInvariantError as exc:
        raise ApplicationError(exc.field, exc.code) from None


def _require_str(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ApplicationError(key, "required")
    return value


def _require_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ApplicationError(key, "must_be_integer")
    return value


def _instant(payload: Mapping[str, object], key: str) -> datetime:
    return parse_utc(payload.get(key), key)


def _governance(payload: Mapping[str, object]) -> GovernanceCommand:
    return GovernanceCommand(
        actor_id=_require_str(payload, "actorId"),
        owner_id=_require_str(payload, "ownerId"),
        approval_id=_approval(payload.get("approvalId")),
        correlation_id=_correlation(payload.get("correlationId")),
        issued_at=_instant(payload, "issuedAt"),
        expires_at=_instant(payload, "expiresAt"),
    )


def _assert_supplier_allowed(snapshot: BuyerSnapshot, token: str) -> None:
    allowed = {item.supplier_token for item in snapshot.offers}
    if snapshot.acceptance is not None:
        allowed = {
            item.supplier_token
            for item in snapshot.offers
            if item.offer_id == snapshot.acceptance.offer_id
        }
    if token not in allowed:
        raise ApplicationError("supplierToken", "isolation_denied")


class FacadeTools:
    def __init__(self, facade: GoldenPathFacade) -> None:
        self._facade = facade

    def get_buyer_snapshot(self, payload: Mapping[str, object]) -> dict[str, object]:
        intent_id = _intent(payload.get("intentId"))
        try:
            return self._facade.get_buyer_snapshot(intent_id).to_primitive()
        except Exception as exc:
            raise map_closed_error(exc) from None

    def create_purchase_intent(self, payload: Mapping[str, object]) -> dict[str, object]:
        try:
            return self._facade.create_purchase_intent(payload).to_primitive()
        except Exception as exc:
            raise map_closed_error(exc) from None

    def confirm_requirement(self, payload: Mapping[str, object]) -> dict[str, object]:
        intent_id = _intent(payload.get("intentId"))
        try:
            return self._facade.confirm_requirement(intent_id, _governance(payload)).to_primitive()
        except Exception as exc:
            raise map_closed_error(exc) from None

    def approve_and_dispatch(self, payload: Mapping[str, object]) -> dict[str, object]:
        intent_id = _intent(payload.get("intentId"))
        try:
            return self._facade.approve_and_dispatch(intent_id, _governance(payload)).to_primitive()
        except Exception as exc:
            raise map_closed_error(exc) from None

    def accept_offer(self, payload: Mapping[str, object]) -> dict[str, object]:
        intent_id = _intent(payload.get("intentId"))
        offer_id = _offer(payload.get("offerId"))
        if "supplierToken" in payload:
            token = _supplier(payload.get("supplierToken"))
            snapshot = self._facade.get_buyer_snapshot(intent_id)
            _assert_supplier_allowed(snapshot, token)
        command = AcceptCommand(
            actor_id=_require_str(payload, "actorId"),
            owner_id=_require_str(payload, "ownerId"),
            approval_id=_approval(payload.get("approvalId")),
            correlation_id=_correlation(payload.get("correlationId")),
            issued_at=_instant(payload, "issuedAt"),
            expires_at=_instant(payload, "expiresAt"),
            offer_id=offer_id,
            offer_version=_require_int(payload, "offerVersion"),
        )
        try:
            return self._facade.accept_recommended_or_selected_offer(
                intent_id, command
            ).to_primitive()
        except Exception as exc:
            raise map_closed_error(exc) from None

    def authorize_simulated_transaction(self, payload: Mapping[str, object]) -> dict[str, object]:
        intent_id = _intent(payload.get("intentId"))
        mode = _require_str(payload, "mode")
        if mode != "SIMULATED":
            raise ApplicationError("mode", "mode_forbidden")
        token = _supplier(payload.get("supplierToken"))
        snapshot = self._facade.get_buyer_snapshot(intent_id)
        _assert_supplier_allowed(snapshot, token)
        command = AuthorizeCommand(
            actor_id=_require_str(payload, "actorId"),
            owner_id=_require_str(payload, "ownerId"),
            approval_id=_approval(payload.get("approvalId")),
            correlation_id=_correlation(payload.get("correlationId")),
            issued_at=_instant(payload, "issuedAt"),
            expires_at=_instant(payload, "expiresAt"),
            acceptance_id=_acceptance(payload.get("acceptanceId")),
            amount_minor=_require_int(payload, "amountMinor"),
            currency=_require_str(payload, "currency"),
            supplier_token=token,
            action=_require_str(payload, "action"),
            mode=mode,
            idempotency_key=_idempotency(payload.get("idempotencyKey")),
        )
        try:
            return self._facade.authorize_simulated_transaction(intent_id, command).to_primitive()
        except Exception as exc:
            raise map_closed_error(exc) from None

    def call(self, name: str, payload: Mapping[str, object]) -> dict[str, object]:
        if name not in CLOSED_TOOLS:
            raise ApplicationError("tool", "unknown")
        method = getattr(self, name)
        return method(payload)  # type: ignore[no-any-return]
