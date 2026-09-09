"""Simulated Offer aggregate and exhaustive state machine."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from itaa_domain.acceptance import Acceptance
from itaa_domain.errors import DomainInvariantError, ExpiredResourceError, OfferVersionMismatchError
from itaa_domain.events import EventType, emit_domain_event
from itaa_domain.identifiers import (
    AcceptanceId,
    CounterOfferId,
    IntentId,
    OfferId,
    SignatureHandle,
    SupplierToken,
)
from itaa_domain.protocol import (
    TransitionRequest,
    TransitionResult,
    assert_monotonic,
    assert_revision,
    permitted_actions,
    reject_illegal,
    require_action_reason,
)
from itaa_domain.value_objects import (
    AddOn,
    CancellationTerm,
    DeclineReason,
    EvidenceRef,
    EvidenceType,
    LotType,
    Money,
    RefundTerm,
    RejectionReason,
    SimulatedAvailability,
    TimeWindow,
    Version,
    format_utc,
    require_distance_metres,
    require_exact_enum,
    require_shuttle_minutes,
    require_utc,
)


class OfferState(StrEnum):
    INVITED = "INVITED"
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    COUNTERED = "COUNTERED"
    VALIDATED = "VALIDATED"
    ELIGIBLE = "ELIGIBLE"
    RECOMMENDED = "RECOMMENDED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"


class OfferAction(StrEnum):
    BEGIN_DRAFT = "begin_draft"
    SUBMIT = "submit"
    VALIDATE = "validate"
    REJECT = "reject"
    COUNTER = "counter"
    RESUBMIT = "resubmit"
    MARK_ELIGIBLE = "mark_eligible"
    RECOMMEND = "recommend"
    ACCEPT = "accept"
    DECLINE = "decline"
    EXPIRE = "expire"


OFFER_TRANSITIONS: dict[tuple[OfferState, OfferAction], OfferState] = {
    (OfferState.INVITED, OfferAction.BEGIN_DRAFT): OfferState.DRAFT,
    (OfferState.DRAFT, OfferAction.SUBMIT): OfferState.SUBMITTED,
    (OfferState.SUBMITTED, OfferAction.VALIDATE): OfferState.VALIDATED,
    (OfferState.SUBMITTED, OfferAction.REJECT): OfferState.REJECTED,
    (OfferState.SUBMITTED, OfferAction.COUNTER): OfferState.COUNTERED,
    (OfferState.COUNTERED, OfferAction.RESUBMIT): OfferState.SUBMITTED,
    (OfferState.COUNTERED, OfferAction.REJECT): OfferState.REJECTED,
    (OfferState.VALIDATED, OfferAction.MARK_ELIGIBLE): OfferState.ELIGIBLE,
    (OfferState.VALIDATED, OfferAction.REJECT): OfferState.REJECTED,
    (OfferState.VALIDATED, OfferAction.EXPIRE): OfferState.EXPIRED,
    (OfferState.ELIGIBLE, OfferAction.RECOMMEND): OfferState.RECOMMENDED,
    (OfferState.ELIGIBLE, OfferAction.ACCEPT): OfferState.ACCEPTED,
    (OfferState.ELIGIBLE, OfferAction.DECLINE): OfferState.DECLINED,
    (OfferState.ELIGIBLE, OfferAction.EXPIRE): OfferState.EXPIRED,
    (OfferState.RECOMMENDED, OfferAction.ACCEPT): OfferState.ACCEPTED,
    (OfferState.RECOMMENDED, OfferAction.DECLINE): OfferState.DECLINED,
    (OfferState.RECOMMENDED, OfferAction.EXPIRE): OfferState.EXPIRED,
}

OFFER_TERMINAL = frozenset(
    {
        OfferState.REJECTED,
        OfferState.EXPIRED,
        OfferState.ACCEPTED,
        OfferState.DECLINED,
    }
)
_OFFER_DUPLICATE_ACTIONS = frozenset(
    {
        OfferAction.REJECT.value,
        OfferAction.EXPIRE.value,
        OfferAction.ACCEPT.value,
        OfferAction.DECLINE.value,
    }
)
_OFFER_EVENT_TYPES = {
    OfferAction.BEGIN_DRAFT: EventType.OFFER_DRAFT_BEGUN,
    OfferAction.SUBMIT: EventType.OFFER_SUBMITTED,
    OfferAction.VALIDATE: EventType.OFFER_VALIDATED,
    OfferAction.REJECT: EventType.OFFER_REJECTED,
    OfferAction.COUNTER: EventType.OFFER_COUNTERED,
    OfferAction.RESUBMIT: EventType.OFFER_RESUBMITTED,
    OfferAction.MARK_ELIGIBLE: EventType.OFFER_MARKED_ELIGIBLE,
    OfferAction.RECOMMEND: EventType.OFFER_RECOMMENDED,
    OfferAction.ACCEPT: EventType.OFFER_ACCEPTED,
    OfferAction.DECLINE: EventType.OFFER_DECLINED,
    OfferAction.EXPIRE: EventType.OFFER_EXPIRED,
}
_OFFER_REASON_TYPES = {
    OfferAction.REJECT: RejectionReason,
    OfferAction.DECLINE: DeclineReason,
}
_TERMS_REQUIRED = frozenset(
    {
        OfferState.SUBMITTED,
        OfferState.COUNTERED,
        OfferState.VALIDATED,
        OfferState.ELIGIBLE,
        OfferState.RECOMMENDED,
        OfferState.REJECTED,
        OfferState.EXPIRED,
        OfferState.ACCEPTED,
        OfferState.DECLINED,
    }
)
_EARLY_STATES = frozenset({OfferState.INVITED, OfferState.DRAFT})
_LIVE_TERMS_STATES = frozenset(
    {
        OfferState.SUBMITTED,
        OfferState.COUNTERED,
        OfferState.VALIDATED,
        OfferState.ELIGIBLE,
        OfferState.RECOMMENDED,
        OfferState.ACCEPTED,
    }
)
_STALE_ADVANCE = frozenset(
    {
        OfferAction.VALIDATE,
        OfferAction.COUNTER,
        OfferAction.MARK_ELIGIBLE,
        OfferAction.RECOMMEND,
        OfferAction.ACCEPT,
    }
)


@dataclass(frozen=True, slots=True)
class OfferPrice:
    subtotal: Money
    fees: Money
    tax: Money
    total: Money

    def __post_init__(self) -> None:
        currency = self.subtotal.currency
        if {self.fees.currency, self.tax.currency, self.total.currency} != {currency}:
            raise DomainInvariantError("currency", "price_currency_mismatch")
        expected = self.subtotal + self.fees + self.tax
        if expected != self.total:
            raise DomainInvariantError("total_minor", "must_equal_components")

    def to_primitive(self) -> dict[str, int | str]:
        return {
            "subtotalMinor": self.subtotal.amount_minor,
            "feesMinor": self.fees.amount_minor,
            "taxMinor": self.tax.amount_minor,
            "totalMinor": self.total.amount_minor,
            "currency": self.total.currency,
        }


@dataclass(frozen=True, slots=True)
class OfferEvidence:
    evidence_type: EvidenceType
    ref: EvidenceRef

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_type, EvidenceType):
            raise DomainInvariantError("evidence_type", "unsupported")

    def to_primitive(self) -> dict[str, str]:
        return {"type": self.evidence_type.value, "ref": self.ref.to_primitive()}


@dataclass(frozen=True, slots=True)
class OfferTerms:
    price: OfferPrice
    lot_type: LotType
    shuttle_minutes: int
    distance_metres: int
    availability: SimulatedAvailability
    add_ons: tuple[AddOn, ...]
    cancellation: CancellationTerm
    refund: RefundTerm
    validity: TimeWindow
    evidence: tuple[OfferEvidence, ...]
    signature: SignatureHandle
    simulation: bool = True

    def __post_init__(self) -> None:
        if self.simulation is not True:
            raise DomainInvariantError("simulation", "must_be_true")
        minutes = require_shuttle_minutes(self.shuttle_minutes)
        metres = require_distance_metres(self.distance_metres)
        if not isinstance(self.lot_type, LotType):
            raise DomainInvariantError("lot_type", "unsupported")
        if not isinstance(self.availability, SimulatedAvailability):
            raise DomainInvariantError("availability", "unsupported")
        if not isinstance(self.cancellation, CancellationTerm):
            raise DomainInvariantError("cancellation", "unsupported")
        if not isinstance(self.refund, RefundTerm):
            raise DomainInvariantError("refund", "unsupported")
        add_ons = tuple(self.add_ons)
        if len(set(add_ons)) != len(add_ons):
            raise DomainInvariantError("add_ons", "duplicate_values")
        for item in add_ons:
            if not isinstance(item, AddOn):
                raise DomainInvariantError("add_ons", "unsupported")
        evidence = tuple(self.evidence)
        if not evidence:
            raise DomainInvariantError("evidence", "required")
        object.__setattr__(self, "shuttle_minutes", minutes)
        object.__setattr__(self, "distance_metres", metres)
        object.__setattr__(self, "add_ons", add_ons)
        object.__setattr__(self, "evidence", evidence)

    def to_primitive(self) -> dict[str, object]:
        return {
            "price": self.price.to_primitive(),
            "lotType": self.lot_type.value,
            "shuttleMinutes": self.shuttle_minutes,
            "distanceMeters": self.distance_metres,
            "availability": self.availability.value,
            "addOns": [item.value for item in self.add_ons],
            "cancellation": self.cancellation.value,
            "refund": self.refund.value,
            "validFrom": format_utc(self.validity.start),
            "validUntil": format_utc(self.validity.end),
            "evidence": [item.to_primitive() for item in self.evidence],
            "signature": self.signature.to_primitive(),
            "simulation": True,
        }


@dataclass(frozen=True, slots=True)
class Offer:
    offer_id: OfferId
    intent_id: IntentId
    supplier_token: SupplierToken
    state: OfferState
    revision: Version
    offer_version: Version
    created_at: datetime
    updated_at: datetime
    simulation: bool = True
    terms: OfferTerms | None = None
    latest_counter_offer_id: CounterOfferId | None = None
    countered_parent_version: Version | None = None
    acceptance_id: AcceptanceId | None = None

    def __post_init__(self) -> None:
        require_exact_enum(self.state, OfferState, "state")
        created = require_utc(self.created_at, "created_at")
        updated = require_utc(self.updated_at, "updated_at")
        if updated < created:
            raise DomainInvariantError("updated_at", "must_not_precede_created_at")
        if self.simulation is not True:
            raise DomainInvariantError("simulation", "must_be_true")
        if self.state in _TERMS_REQUIRED and self.terms is None:
            raise DomainInvariantError("terms", "required")
        if self.state == OfferState.INVITED and self.revision != Version.initial():
            raise DomainInvariantError("revision", "invited_must_start_at_one")
        if self.state in _EARLY_STATES:
            if (
                self.latest_counter_offer_id is not None
                or self.countered_parent_version is not None
            ):
                raise DomainInvariantError("counter_offer", "must_be_absent")
            if self.acceptance_id is not None:
                raise DomainInvariantError("acceptance_id", "must_be_absent")
        if self.state is OfferState.COUNTERED:
            if self.latest_counter_offer_id is None or self.countered_parent_version is None:
                raise DomainInvariantError("counter_offer", "required")
            if self.countered_parent_version != self.offer_version:
                raise DomainInvariantError("countered_parent_version", "mismatch")
        if self.state is OfferState.ACCEPTED and self.acceptance_id is None:
            raise DomainInvariantError("acceptance_id", "required")
        if self.state is not OfferState.ACCEPTED and self.acceptance_id is not None:
            raise DomainInvariantError("acceptance_id", "must_be_absent")
        if self.terms is not None:
            valid_until = self.terms.validity.end
            if self.state is OfferState.EXPIRED and updated < valid_until:
                raise DomainInvariantError("updated_at", "not_yet_expired")
            if self.state in _LIVE_TERMS_STATES and updated >= valid_until:
                raise DomainInvariantError("updated_at", "offer_expired")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "updated_at", updated)

    @classmethod
    def invite(
        cls,
        *,
        offer_id: OfferId,
        intent_id: IntentId,
        supplier_token: SupplierToken,
        created_at: datetime,
    ) -> Offer:
        return cls(
            offer_id=offer_id,
            intent_id=intent_id,
            supplier_token=supplier_token,
            state=OfferState.INVITED,
            revision=Version.initial(),
            offer_version=Version.initial(),
            created_at=created_at,
            updated_at=created_at,
            simulation=True,
        )

    def permitted_actions(self) -> tuple[str, ...]:
        return permitted_actions(OFFER_TRANSITIONS, self.state)

    def begin_draft(self, request: TransitionRequest) -> TransitionResult[Offer]:
        return self._transition(OfferAction.BEGIN_DRAFT, request)

    def submit(self, request: TransitionRequest, terms: OfferTerms) -> TransitionResult[Offer]:
        return self._transition(OfferAction.SUBMIT, request, terms=terms)

    def validate(self, request: TransitionRequest) -> TransitionResult[Offer]:
        return self._transition(OfferAction.VALIDATE, request)

    def reject(
        self,
        request: TransitionRequest,
        reason: RejectionReason,
    ) -> TransitionResult[Offer]:
        return self._transition(OfferAction.REJECT, request, reason=reason)

    def counter(
        self,
        request: TransitionRequest,
        counter_offer_id: CounterOfferId,
        parent_offer_version: Version,
    ) -> TransitionResult[Offer]:
        return self._transition(
            OfferAction.COUNTER,
            request,
            counter_offer_id=counter_offer_id,
            parent_offer_version=parent_offer_version,
        )

    def resubmit(
        self,
        request: TransitionRequest,
        terms: OfferTerms,
        new_offer_version: Version,
    ) -> TransitionResult[Offer]:
        return self._transition(
            OfferAction.RESUBMIT,
            request,
            terms=terms,
            new_offer_version=new_offer_version,
        )

    def mark_eligible(self, request: TransitionRequest) -> TransitionResult[Offer]:
        return self._transition(OfferAction.MARK_ELIGIBLE, request)

    def recommend(self, request: TransitionRequest) -> TransitionResult[Offer]:
        return self._transition(OfferAction.RECOMMEND, request)

    def accept(self, request: TransitionRequest, acceptance: Acceptance) -> TransitionResult[Offer]:
        return self._transition(OfferAction.ACCEPT, request, acceptance=acceptance)

    def decline(
        self,
        request: TransitionRequest,
        reason: DeclineReason,
    ) -> TransitionResult[Offer]:
        return self._transition(OfferAction.DECLINE, request, reason=reason)

    def expire(self, request: TransitionRequest) -> TransitionResult[Offer]:
        return self._transition(OfferAction.EXPIRE, request)

    def apply(
        self,
        action: OfferAction,
        request: TransitionRequest,
        *,
        terms: OfferTerms | None = None,
        reason: RejectionReason | DeclineReason | None = None,
        counter_offer_id: CounterOfferId | None = None,
        parent_offer_version: Version | None = None,
        new_offer_version: Version | None = None,
        acceptance: Acceptance | None = None,
    ) -> TransitionResult[Offer]:
        return self._transition(
            action,
            request,
            terms=terms,
            reason=reason,
            counter_offer_id=counter_offer_id,
            parent_offer_version=parent_offer_version,
            new_offer_version=new_offer_version,
            acceptance=acceptance,
        )

    def to_primitive(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "offerId": self.offer_id.to_primitive(),
            "intentId": self.intent_id.to_primitive(),
            "supplierToken": self.supplier_token.to_primitive(),
            "state": self.state.value,
            "revision": self.revision.to_primitive(),
            "offerVersion": self.offer_version.to_primitive(),
            "createdAt": format_utc(self.created_at),
            "updatedAt": format_utc(self.updated_at),
            "simulation": True,
        }
        if self.terms is not None:
            payload["terms"] = self.terms.to_primitive()
        if self.latest_counter_offer_id is not None:
            payload["latestCounterOfferId"] = self.latest_counter_offer_id.to_primitive()
        if self.countered_parent_version is not None:
            payload["counteredParentVersion"] = self.countered_parent_version.to_primitive()
        if self.acceptance_id is not None:
            payload["acceptanceId"] = self.acceptance_id.to_primitive()
        return payload

    def _transition(
        self,
        action: OfferAction,
        request: TransitionRequest,
        *,
        terms: OfferTerms | None = None,
        reason: RejectionReason | DeclineReason | None = None,
        counter_offer_id: CounterOfferId | None = None,
        parent_offer_version: Version | None = None,
        new_offer_version: Version | None = None,
        acceptance: Acceptance | None = None,
    ) -> TransitionResult[Offer]:
        require_exact_enum(action, OfferAction, "action")
        assert_revision(
            self.revision,
            request.expected_revision,
            "offer",
            self.offer_id.to_primitive(),
        )
        target = OFFER_TRANSITIONS.get((self.state, action))
        if target is None:
            reject_illegal(
                resource_type="offer",
                resource_id=self.offer_id.to_primitive(),
                current_state=self.state.value,
                attempted_action=action.value,
                permitted=self.permitted_actions(),
                terminal=self.state in OFFER_TERMINAL,
                duplicate_actions=_OFFER_DUPLICATE_ACTIONS,
            )
            raise AssertionError("unreachable")
        assert_monotonic(self.updated_at, request.occurred_at)
        next_terms = self.terms
        next_offer_version = self.offer_version
        next_counter = self.latest_counter_offer_id
        next_parent = self.countered_parent_version
        next_acceptance_id = self.acceptance_id
        reason_code = require_action_reason(
            reason,
            _OFFER_REASON_TYPES.get(action),
            action_code=action.value,
        )
        if action is OfferAction.SUBMIT:
            if terms is None:
                raise DomainInvariantError("terms", "required")
            if request.occurred_at >= terms.validity.end:
                raise ExpiredResourceError(
                    resource_type="offer",
                    resource_id=self.offer_id.to_primitive(),
                    expired_at=format_utc(terms.validity.end),
                )
            next_terms = terms
        if (
            action in _STALE_ADVANCE
            and self.terms is not None
            and request.occurred_at >= self.terms.validity.end
        ):
            raise ExpiredResourceError(
                resource_type="offer",
                resource_id=self.offer_id.to_primitive(),
                expired_at=format_utc(self.terms.validity.end),
            )
        if action is OfferAction.COUNTER:
            if counter_offer_id is None or parent_offer_version is None:
                raise DomainInvariantError("counter_offer", "required")
            if parent_offer_version != self.offer_version:
                raise OfferVersionMismatchError(
                    offer_id=self.offer_id.to_primitive(),
                    expected_version=self.offer_version.value,
                    actual_version=parent_offer_version.value,
                )
            next_counter = counter_offer_id
            next_parent = parent_offer_version
        if action is OfferAction.RESUBMIT:
            if terms is None or new_offer_version is None:
                raise DomainInvariantError("offer_version", "required")
            if new_offer_version != self.offer_version.next():
                raise OfferVersionMismatchError(
                    offer_id=self.offer_id.to_primitive(),
                    expected_version=self.offer_version.next().value,
                    actual_version=new_offer_version.value,
                )
            if request.occurred_at >= terms.validity.end:
                raise ExpiredResourceError(
                    resource_type="offer",
                    resource_id=self.offer_id.to_primitive(),
                    expired_at=format_utc(terms.validity.end),
                )
            next_terms = terms
            next_offer_version = new_offer_version
        if action is OfferAction.ACCEPT:
            if acceptance is None:
                raise DomainInvariantError("acceptance", "required")
            if acceptance.offer_id != self.offer_id:
                raise DomainInvariantError("offer_id", "mismatch")
            if acceptance.intent_id != self.intent_id:
                raise DomainInvariantError("intent_id", "mismatch")
            if acceptance.offer_version != self.offer_version:
                raise OfferVersionMismatchError(
                    offer_id=self.offer_id.to_primitive(),
                    expected_version=self.offer_version.value,
                    actual_version=acceptance.offer_version.value,
                )
            if (
                request.occurred_at < acceptance.created_at
                or request.occurred_at >= acceptance.expires_at
            ):
                raise ExpiredResourceError(
                    resource_type="acceptance",
                    resource_id=acceptance.acceptance_id.to_primitive(),
                    expired_at=format_utc(acceptance.expires_at),
                )
            next_acceptance_id = acceptance.acceptance_id
        if action is OfferAction.EXPIRE and next_terms is None:
            raise DomainInvariantError("terms", "required")
        if (
            action is OfferAction.EXPIRE
            and next_terms is not None
            and request.occurred_at < next_terms.validity.end
        ):
            raise DomainInvariantError("valid_until", "not_yet_expired")
        updated = replace(
            self,
            state=target,
            revision=self.revision.next(),
            offer_version=next_offer_version,
            updated_at=request.occurred_at,
            terms=next_terms,
            latest_counter_offer_id=next_counter,
            countered_parent_version=next_parent,
            acceptance_id=next_acceptance_id,
        )
        event = emit_domain_event(
            event_type=_OFFER_EVENT_TYPES[action],
            resource_id=self.offer_id.to_primitive(),
            resource_version=updated.revision.value,
            occurred_at=request.occurred_at,
            actor_type=request.actor.category,
            actor_id=request.actor.actor_id.to_primitive(),
            reason_code=reason_code,
            correlation_id=request.correlation_id.to_primitive(),
            intent_id=self.intent_id.to_primitive(),
            offer_id=self.offer_id.to_primitive(),
            acceptance_id=(
                acceptance.acceptance_id.to_primitive() if acceptance is not None else None
            ),
            counter_offer_id=next_counter.to_primitive() if next_counter is not None else None,
            offer_version=updated.offer_version.value,
            simulation=True,
        )
        return TransitionResult(updated, event)
