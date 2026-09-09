"""Read facade for orchestration Intent, Plan, Ledger, and Booking Task."""

from __future__ import annotations

from collections.abc import Mapping

from itaa_application.compatibility import CompatibilityAdapter, ResolvedKind, WrapperIds
from itaa_application.cost_ledger_projection import (
    LedgerOfferInput,
    LedgerTaskInput,
    project_cost_ledger,
)
from itaa_application.errors import ApplicationError
from itaa_application.freeze import thaw_payload
from itaa_application.golden_path import GoldenPathFacade
from itaa_application.plan_projection import PlanTaskInput, project_plan
from itaa_application.session_models import (
    BuyerSessionState,
    BuyerSnapshot,
    GoldenPathSession,
    RankedOfferView,
)
from itaa_domain.booking_task_states import BookingTaskState
from itaa_domain.errors import DomainInvariantError
from itaa_domain.identifiers import IntentId
from itaa_domain.intent_states import (
    ParentLifecycle,
    TaskMembership,
    TaskProjectionInput,
    project_intent_state,
)
from itaa_domain.value_objects import format_utc

_SUPPLIER_BOUND_KEYS = (
    "taskId",
    "domain",
    "state",
    "simulation",
    "requirementVersion",
    "validity",
    "inventory",
    "transactionResult",
)
_SUPPLIER_FORBIDDEN = frozenset(
    {
        "intentId",
        "conversationId",
        "planId",
        "ledgerId",
        "purchaseIntentId",
        "siblings",
        "siblingTaskIds",
        "taskIds",
        "offers",
        "competitorOffers",
        "preferences",
        "buyerToken",
        "buyerId",
        "objective",
    }
)


def supplier_bound_fields(task: Mapping[str, object]) -> dict[str, object]:
    """Fields safe to expose toward a supplier. Isolation is structural."""
    bound = {key: task[key] for key in _SUPPLIER_BOUND_KEYS if key in task}
    if _SUPPLIER_FORBIDDEN.intersection(bound):
        raise ApplicationError("internal", "closed")
    return bound


def map_buyer_session(session: GoldenPathSession) -> tuple[ParentLifecycle, BookingTaskState]:
    state = session.state
    if state is BuyerSessionState.AWAITING_REQUIREMENT_CONFIRMATION:
        return ParentLifecycle.NONE, BookingTaskState.A1_REVIEW
    if state is BuyerSessionState.AWAITING_DISPATCH_APPROVAL:
        return ParentLifecycle.NONE, BookingTaskState.A2_REQUIRED
    if state is BuyerSessionState.OFFERS_RANKED:
        return ParentLifecycle.NONE, BookingTaskState.OFFERS_READY
    if state is BuyerSessionState.ACCEPTANCE_RECORDED:
        return ParentLifecycle.NONE, BookingTaskState.A4_REQUIRED
    if state is BuyerSessionState.TRANSACTION_AUTHORIZED_SIMULATED:
        return ParentLifecycle.NONE, BookingTaskState.AUTHORIZED_SIMULATED
    if state is BuyerSessionState.CANCELLED:
        if _dispatched(session):
            return ParentLifecycle.CANCELLED, BookingTaskState.CANCELLED
        return ParentLifecycle.DELETED, BookingTaskState.CANCELLED
    if state is BuyerSessionState.SUPERSEDED:
        return ParentLifecycle.CANCELLED, BookingTaskState.SUPERSEDED
    return ParentLifecycle.NONE, BookingTaskState.A1_REVIEW


class OrchestrationService:
    def __init__(
        self,
        facade: GoldenPathFacade,
        adapter: CompatibilityAdapter | None = None,
    ) -> None:
        self._facade = facade
        self._adapter = adapter or CompatibilityAdapter()

    def get_intent(self, raw_id: str) -> dict[str, object]:
        session, ids = self._resolve_session(raw_id)
        return self._intent_document(session, ids)

    def get_plan(self, raw_id: str) -> dict[str, object]:
        session, ids = self._resolve_session(raw_id)
        overlay, task_state = map_buyer_session(session)
        del overlay
        return project_plan(
            ids.orchestration_intent_id,
            ids.plan_id,
            (
                PlanTaskInput(
                    task_id=ids.booking_task_id,
                    membership=TaskMembership.ACCEPTED,
                    state=task_state,
                ),
            ),
        )

    def get_ledger(self, raw_id: str) -> dict[str, object]:
        session, ids = self._resolve_session(raw_id)
        snapshot = self._facade.get_buyer_snapshot(session.intent_id)
        _, task_state = map_buyer_session(session)
        return project_cost_ledger(
            ids.orchestration_intent_id,
            ids.ledger_id,
            (self._ledger_task(ids.booking_task_id, task_state, session, snapshot),),
            simulation=True,
        )

    def get_task(self, raw_id: str, raw_task_id: str) -> dict[str, object]:
        session, ids = self._resolve_session(raw_id)
        task_id = self._adapter.require_booking_task_id(raw_task_id)
        if task_id != ids.booking_task_id:
            raise ApplicationError("taskId", "unknown_resource")
        return self._booking_task(session, ids)

    def _resolve_session(self, raw_id: str) -> tuple[GoldenPathSession, WrapperIds]:
        ref = self._adapter.resolve_orchestration_ref(raw_id)
        if ref.kind is ResolvedKind.MALFORMED:
            raise ApplicationError("intentId", "invalid_opaque_syntax")
        if ref.kind is ResolvedKind.PURCHASE_ALIAS:
            return self._session_for_purchase(ref.value)
        purchase_id = self._adapter.purchase_intent_id_for(ref.value)
        if purchase_id is None:
            raise ApplicationError("intentId", "unknown_resource")
        return self._session_for_purchase(purchase_id)

    def _session_for_purchase(
        self, purchase_intent_id: str
    ) -> tuple[GoldenPathSession, WrapperIds]:
        try:
            intent_id = IntentId(purchase_intent_id)
        except DomainInvariantError:
            raise ApplicationError("intentId", "invalid_opaque_syntax") from None
        session = self._facade.lookup_session(intent_id)
        if session is None:
            raise ApplicationError("intentId", "unknown_resource")
        return session, self._adapter.wrap_purchase_intent(session)

    def _intent_document(self, session: GoldenPathSession, ids: WrapperIds) -> dict[str, object]:
        overlay, task_state = map_buyer_session(session)
        parent = project_intent_state(
            overlay=overlay,
            tasks=(TaskProjectionInput(membership=TaskMembership.ACCEPTED, state=task_state),),
        )
        return {
            "schemaVersion": "1.0",
            "intentId": ids.orchestration_intent_id,
            "state": parent.value,
            "objective": _objective(session),
            "createdAt": format_utc(session.purchase_intent.created_at),
            "updatedAt": format_utc(session.purchase_intent.updated_at),
            "simulation": True,
            "durability": "unsupported",
            "planId": ids.plan_id,
            "ledgerId": ids.ledger_id,
        }

    def _booking_task(self, session: GoldenPathSession, ids: WrapperIds) -> dict[str, object]:
        snapshot = self._facade.get_buyer_snapshot(session.intent_id)
        _, task_state = map_buyer_session(session)
        payload: dict[str, object] = {
            "schemaVersion": "1.0",
            "taskId": ids.booking_task_id,
            "intentId": ids.orchestration_intent_id,
            "domain": "parking",
            "state": task_state.value,
            "simulation": True,
            "requirementVersion": session.requirement.revision.to_primitive(),
            "purchaseIntentId": ids.purchase_intent_id,
            "validity": _task_validity(session, snapshot),
            "inventory": "not_held",
            "transactionResult": _task_transaction_result(session),
        }
        return payload

    def _ledger_task(
        self,
        task_id: str,
        task_state: BookingTaskState,
        session: GoldenPathSession,
        snapshot: BuyerSnapshot,
    ) -> LedgerTaskInput:
        selected_id = (
            None if session.acceptance is None else session.acceptance.offer_id.to_primitive()
        )
        authorized = session.state is BuyerSessionState.TRANSACTION_AUTHORIZED_SIMULATED
        offers = tuple(
            _ledger_offer(item, selected_id=selected_id, authorized=authorized)
            for item in snapshot.offers
        )
        return LedgerTaskInput(task_id=task_id, state=task_state, offers=offers)


def _dispatched(session: GoldenPathSession) -> bool:
    if session.collection is not None:
        return True
    if session.mapped_offers:
        return True
    if session.decision is not None:
        return True
    return session.state is BuyerSessionState.SUPERSEDED


def _objective(session: GoldenPathSession) -> str:
    thawed = thaw_payload(session.intent_payload)
    if isinstance(thawed, dict):
        raw = thawed.get("objective")
        if isinstance(raw, str) and raw.strip():
            return raw
    return f"Airport parking {session.requirement.airport.to_primitive()}"


def _task_validity(session: GoldenPathSession, snapshot: BuyerSnapshot) -> str:
    selected_id = None if session.acceptance is None else session.acceptance.offer_id.to_primitive()
    if selected_id is not None:
        for item in snapshot.offers:
            if item.offer_id == selected_id:
                return item.validity
    for item in snapshot.offers:
        if item.recommended:
            return item.validity
    if snapshot.offers:
        return snapshot.offers[0].validity
    return "valid"


def _task_transaction_result(session: GoldenPathSession) -> str:
    if session.state is BuyerSessionState.TRANSACTION_AUTHORIZED_SIMULATED:
        return "authorized_simulated"
    return "simulated"


def _ledger_offer(
    item: RankedOfferView,
    *,
    selected_id: str | None,
    authorized: bool,
) -> LedgerOfferInput:
    selected = item.offer_id == selected_id
    return LedgerOfferInput(
        total_minor=item.total_minor,
        tax_minor=item.tax_minor,
        fees_minor=item.fees_minor,
        currency=item.currency,
        validity=item.validity,
        recommended=item.recommended,
        selected=selected,
        authorized=selected and authorized,
    )
