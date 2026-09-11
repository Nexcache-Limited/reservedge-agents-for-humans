"""Closed Buyer Orchestrator tools. Plan tools cannot mutate; execute tools cannot skip A1–A4."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Final

from itaa_application.errors import ApplicationError
from itaa_application.external_search_port import (
    ExperienceSearchPort,
    ExternalSearchPort,
    ExternalSearchQuery,
    PlaceRef,
    public_experience_search_result,
    public_search_result,
)
from itaa_application.golden_path import GoldenPathFacade, map_closed_error
from itaa_application.session_models import (
    AcceptCommand,
    AuthorizeCommand,
    BuyerSnapshot,
    GovernanceCommand,
)
from itaa_aws_adapter.fake import parking_fields_from_objective
from itaa_aws_adapter.projector import capabilities, extract_facts, project_plan
from itaa_aws_adapter.schemas import PlanAnswers
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

PLAN_TOOLS: Final[tuple[str, ...]] = (
    "get_supported_capabilities",
    "project_plan_from_facts",
)
EXECUTE_TOOLS: Final[tuple[str, ...]] = (
    "prepare_parking_requirement",
    "search_stay_offers",
    "search_experience_offers",
    "book_stay_sandbox",
    "get_buyer_snapshot",
    "solicit_parking_offers",
    "explain_ranked_offers",
    "accept_offer",
    "authorize_simulated_transaction",
)
CLOSED_TOOLS: Final[tuple[str, ...]] = PLAN_TOOLS + EXECUTE_TOOLS
MUTATING_EXECUTE_TOOLS: Final[frozenset[str]] = frozenset(
    {
        "solicit_parking_offers",
        "accept_offer",
        "authorize_simulated_transaction",
        "book_stay_sandbox",
    }
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


class ClosedTools:
    def __init__(
        self,
        facade: GoldenPathFacade | None = None,
        stay_search: ExternalSearchPort | None = None,
        experience_search: ExperienceSearchPort | None = None,
    ) -> None:
        self._facade = facade
        if stay_search is None:
            from itaa_liteapi_hotels.compose import compose_stay_search_port

            stay_search = compose_stay_search_port()
        if experience_search is None:
            from itaa_prioticket_experiences.compose import compose_experience_search_port

            experience_search = compose_experience_search_port()
        self._stay_search = stay_search
        self._experience_search = experience_search

    def get_supported_capabilities(self, payload: Mapping[str, object]) -> dict[str, object]:
        del payload
        return dict(capabilities())

    def project_plan_from_facts(self, payload: Mapping[str, object]) -> dict[str, object]:
        objective = _require_str(payload, "objective")
        answers = PlanAnswers.model_validate(payload.get("answers") or {})
        return project_plan(objective, answers).model_dump(mode="json")

    def prepare_parking_requirement(self, payload: Mapping[str, object]) -> dict[str, object]:
        if payload.get("planConfirmed") is not True:
            raise ApplicationError("plan", "illegal_state")
        objective = _require_str(payload, "objective")
        facts = extract_facts(objective, PlanAnswers.model_validate(payload.get("answers") or {}))
        fields = parking_fields_from_objective(objective, facts)
        if "intentId" in fields or "buyerToken" in fields:
            raise ApplicationError("internal", "closed")
        return fields

    def search_stay_offers(self, payload: Mapping[str, object]) -> dict[str, object]:
        destination = str(payload.get("destination") or "").strip()
        check_in = str(payload.get("checkIn") or "").strip()
        check_out = str(payload.get("checkOut") or "").strip()
        origin_raw = str(payload.get("origin") or "").strip()
        guests_raw = payload.get("guests")
        guests: int | None = None
        if isinstance(guests_raw, int) and not isinstance(guests_raw, bool):
            guests = guests_raw
        query = ExternalSearchQuery(
            domain="stay",
            destination=PlaceRef("city", destination),
            start=check_in,
            end=check_out,
            origin=PlaceRef("city", origin_raw) if origin_raw else None,
            guests=guests,
            correlation_id=str(payload.get("correlationId") or ""),
        )
        result = self._stay_search.search(query)
        return public_search_result(result)

    def search_experience_offers(self, payload: Mapping[str, object]) -> dict[str, object]:
        destination = str(payload.get("destination") or "").strip()
        start = str(payload.get("start") or payload.get("checkIn") or "").strip()
        end = str(payload.get("end") or payload.get("checkOut") or "").strip()
        prefs_raw = payload.get("preferences")
        preferences: tuple[str, ...] = ()
        if isinstance(prefs_raw, list):
            preferences = tuple(str(item).strip() for item in prefs_raw if str(item).strip())
        query = ExternalSearchQuery(
            domain="experience",
            destination=PlaceRef("city", destination),
            start=start,
            end=end,
            preferences=preferences,
            correlation_id=str(payload.get("correlationId") or ""),
        )
        result = self._experience_search.search(query)
        public = public_experience_search_result(result)
        encoded = str(public).lower()
        if (
            "itaa_prioticket_client_secret" in encoded
            or "client_secret" in encoded
            or "x-api-key" in encoded
        ):
            raise ApplicationError("experienceSearch", "closed")
        return public

    def book_stay_sandbox(self, payload: Mapping[str, object]) -> dict[str, object]:
        rate_ref = str(payload.get("rateRef") or "").strip()
        if not rate_ref:
            raise ApplicationError("rateRef", "required")
        book = getattr(self._stay_search, "book_sandbox", None)
        if not callable(book):
            raise ApplicationError("staySearch", "unavailable")
        result = book(rate_ref)
        if not isinstance(result, dict):
            raise ApplicationError("staySearch", "unavailable")
        public = {
            "status": str(result.get("status") or "unavailable"),
            "phase": str(result.get("phase") or "stopped"),
            "source": str(result.get("source") or ""),
            "simulatedPayment": result.get("simulatedPayment") is True,
            "bookingId": str(result.get("bookingId") or "")[:80],
            "buyerSafeMessage": str(
                result.get("buyerSafeMessage") or "Sandbox booking stopped. No charge."
            ),
        }
        encoded = str(public).lower()
        if "x-api-key" in encoded or "itaa_liteapi_api_key" in encoded:
            raise ApplicationError("staySearch", "closed")
        return public

    def get_buyer_snapshot(self, payload: Mapping[str, object]) -> dict[str, object]:
        facade = self._require_facade()
        intent_id = _intent(payload.get("intentId"))
        try:
            return facade.get_buyer_snapshot(intent_id).to_primitive()
        except Exception as exc:
            raise map_closed_error(exc) from None

    def solicit_parking_offers(self, payload: Mapping[str, object]) -> dict[str, object]:
        self._require_grant(payload)
        facade = self._require_facade()
        intent_id = _intent(payload.get("intentId"))
        try:
            return facade.approve_and_dispatch(intent_id, _governance(payload)).to_primitive()
        except Exception as exc:
            raise map_closed_error(exc) from None

    def explain_ranked_offers(self, payload: Mapping[str, object]) -> dict[str, object]:
        facade = self._require_facade()
        intent_id = _intent(payload.get("intentId"))
        try:
            snapshot = facade.get_buyer_snapshot(intent_id)
        except Exception as exc:
            raise map_closed_error(exc) from None
        winner = next(
            (item for item in snapshot.offers if item.offer_id == snapshot.recommended_offer_id),
            None,
        )
        scores = [item.score_micros for item in snapshot.offers]
        totals = [item.total_minor for item in snapshot.offers]
        if winner is None:
            explanation = "No recommendation is available yet."
        else:
            explanation = f"The recommended offer is rank {winner.rank} from deterministic ranking."
        return {
            "explanation": explanation,
            "recommendedOfferId": snapshot.recommended_offer_id,
            "rank": None if winner is None else winner.rank,
            "scoreMicros": scores,
            "totalMinor": totals,
            "grounded": True,
        }

    def accept_offer(self, payload: Mapping[str, object]) -> dict[str, object]:
        self._require_grant(payload)
        facade = self._require_facade()
        intent_id = _intent(payload.get("intentId"))
        offer_id = _offer(payload.get("offerId"))
        if "supplierToken" in payload:
            token = _supplier(payload.get("supplierToken"))
            snapshot = facade.get_buyer_snapshot(intent_id)
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
            return facade.accept_recommended_or_selected_offer(intent_id, command).to_primitive()
        except Exception as exc:
            raise map_closed_error(exc) from None

    def authorize_simulated_transaction(self, payload: Mapping[str, object]) -> dict[str, object]:
        self._require_grant(payload)
        facade = self._require_facade()
        intent_id = _intent(payload.get("intentId"))
        mode = _require_str(payload, "mode")
        if mode != "SIMULATED":
            raise ApplicationError("mode", "mode_forbidden")
        token = _supplier(payload.get("supplierToken"))
        snapshot = facade.get_buyer_snapshot(intent_id)
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
            return facade.authorize_simulated_transaction(intent_id, command).to_primitive()
        except Exception as exc:
            raise map_closed_error(exc) from None

    def call(self, name: str, payload: Mapping[str, object], *, turn: str) -> dict[str, object]:
        if name not in CLOSED_TOOLS:
            raise ApplicationError("tool", "closed")
        if turn == "plan" and name not in PLAN_TOOLS:
            raise ApplicationError("tool", "closed")
        if turn == "execute" and name not in EXECUTE_TOOLS:
            raise ApplicationError("tool", "closed")
        method = getattr(self, name)
        return method(payload)  # type: ignore[no-any-return]

    def _require_facade(self) -> GoldenPathFacade:
        if self._facade is None:
            raise ApplicationError("internal", "closed")
        return self._facade

    def _require_grant(self, payload: Mapping[str, object]) -> None:
        if not payload.get("approvalId"):
            raise ApplicationError("approvalId", "required")
