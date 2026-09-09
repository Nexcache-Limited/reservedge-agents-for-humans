"""Purchase-intent compatibility mapping. The only prefix-aware product module."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from itaa_application.errors import ApplicationError
from itaa_application.session_models import GoldenPathSession
from itaa_domain.errors import DomainInvariantError
from itaa_domain.identifiers import (
    BookingTaskId,
    IntentId,
    LedgerId,
    OrchestrationIntentId,
    PlanId,
)


class ResolvedKind(StrEnum):
    ORCHESTRATION = "orchestration"
    PURCHASE_ALIAS = "purchase_alias"
    MALFORMED = "malformed"


@dataclass(frozen=True, slots=True)
class ResolvedRef:
    kind: ResolvedKind
    value: str


@dataclass(frozen=True, slots=True)
class WrapperIds:
    orchestration_intent_id: str
    booking_task_id: str
    plan_id: str
    ledger_id: str
    purchase_intent_id: str


def resolve_orchestration_ref(raw: str) -> ResolvedRef:
    if not isinstance(raw, str):
        return ResolvedRef(ResolvedKind.MALFORMED, "")
    try:
        return ResolvedRef(ResolvedKind.ORCHESTRATION, OrchestrationIntentId(raw).to_primitive())
    except DomainInvariantError:
        pass
    try:
        return ResolvedRef(ResolvedKind.PURCHASE_ALIAS, IntentId(raw).to_primitive())
    except DomainInvariantError:
        return ResolvedRef(ResolvedKind.MALFORMED, raw)


def wrapper_ids_from_purchase_intent(purchase_intent_id: str) -> WrapperIds:
    try:
        validated = IntentId(purchase_intent_id).to_primitive()
    except DomainInvariantError as exc:
        raise ApplicationError("intentId", exc.code) from None
    if not validated.startswith("pi_"):
        raise ApplicationError("intentId", "invalid_opaque_syntax")
    body = validated[3:]
    try:
        return WrapperIds(
            orchestration_intent_id=OrchestrationIntentId("oi_" + body).to_primitive(),
            booking_task_id=BookingTaskId("bt_" + body).to_primitive(),
            plan_id=PlanId("pl_" + body).to_primitive(),
            ledger_id=LedgerId("ld_" + body).to_primitive(),
            purchase_intent_id=validated,
        )
    except DomainInvariantError as exc:
        raise ApplicationError("intentId", exc.code) from None


class CompatibilityAdapter:
    """Process-local reverse index from wrapped oi_* identities back to pi_*."""

    def __init__(self) -> None:
        self._oi_to_pi: dict[str, str] = {}
        self._wrapped: dict[str, WrapperIds] = {}

    def resolve_orchestration_ref(self, raw: str) -> ResolvedRef:
        return resolve_orchestration_ref(raw)

    def wrap_purchase_intent(self, session: GoldenPathSession) -> WrapperIds:
        purchase_intent_id = session.purchase_intent.intent_id.to_primitive()
        existing = self._wrapped.get(purchase_intent_id)
        if existing is not None:
            return existing
        ids = wrapper_ids_from_purchase_intent(purchase_intent_id)
        self._wrapped[purchase_intent_id] = ids
        self._oi_to_pi[ids.orchestration_intent_id] = purchase_intent_id
        return ids

    def require_booking_task_id(self, raw: str) -> str:
        try:
            return BookingTaskId(raw).to_primitive()
        except DomainInvariantError as exc:
            raise ApplicationError("taskId", exc.code) from None

    def purchase_intent_id_for(self, orchestration_id: str) -> str | None:
        cached = self._oi_to_pi.get(orchestration_id)
        if cached is not None:
            return cached
        try:
            canonical = OrchestrationIntentId(orchestration_id).to_primitive()
        except DomainInvariantError:
            return None
        if not canonical.startswith("oi_"):
            return None
        derived = "pi_" + canonical[3:]
        try:
            return IntentId(derived).to_primitive()
        except DomainInvariantError:
            return None
