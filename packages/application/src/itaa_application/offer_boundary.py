"""Buyer-side Offer validation from a sealed authorized collection response."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from pydantic import ValidationError

from itaa_application.errors import ApplicationError
from itaa_application.freeze import freeze_payload, thaw_payload
from itaa_application.policy_evaluation import TrustedPolicyEvaluation
from itaa_application.supplier_port import ClosedReason, TerminalKind, validity_duration_in_bounds
from itaa_contracts_generated.offer import Offer as ContractOffer
from itaa_domain.errors import DomainInvariantError, ExpiredResourceError
from itaa_domain.identifiers import (
    ActorId,
    BuyerToken,
    CorrelationId,
    IntentId,
    OfferId,
    SignatureHandle,
    SupplierToken,
)
from itaa_domain.offer import Offer, OfferEvidence, OfferPrice, OfferState, OfferTerms
from itaa_domain.protocol import TransitionRequest
from itaa_domain.value_objects import (
    JS_SAFE_MAX,
    ActorRef,
    ActorType,
    AddOn,
    CancellationTerm,
    CoveredPreference,
    EvidenceRef,
    EvidenceType,
    LotType,
    Money,
    PayloadHash,
    RefundTerm,
    SimulatedAvailability,
    TimeWindow,
    Version,
    parse_utc,
    require_shuttle_minutes,
    require_utc,
)
from itaa_policy.envelopes import DispatchAuthorization, SupplierEnvelope
from itaa_policy.isolation import SupplierInvitationToken
from itaa_ranking.inputs import RankingNeed, RankingOffer

_REPRESENTABLE_ADD_ONS = {item.value: item for item in AddOn}


def _require_dict(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ApplicationError(field, "required")
    return value


def _require_str(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ApplicationError(field, "required")
    return value


@dataclass(frozen=True, slots=True, init=False)
class AuthorizedResponseBinding:
    """Sealed dispatch + channel binding. Direct construction is impossible."""

    authorization: DispatchAuthorization
    correlation_id: CorrelationId

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise ApplicationError("binding", "sealed")

    @classmethod
    def from_authorization(
        cls,
        authorization: DispatchAuthorization,
        *,
        correlation_id: CorrelationId,
    ) -> AuthorizedResponseBinding:
        if type(authorization) is not DispatchAuthorization:
            raise ApplicationError("authorization", "required")
        if not authorization.allowed or authorization.envelope is None:
            raise ApplicationError("authorization", "denied")
        if type(authorization.envelope) is not SupplierEnvelope:
            raise ApplicationError("envelope", "required")
        if type(correlation_id) is not CorrelationId:
            raise ApplicationError("correlation_id", "invalid_opaque_syntax")
        self = object.__new__(cls)
        object.__setattr__(self, "authorization", authorization)
        object.__setattr__(self, "correlation_id", correlation_id)
        self._payload()
        return self

    @property
    def envelope(self) -> SupplierEnvelope:
        envelope = self.authorization.envelope
        if envelope is None:
            raise ApplicationError("envelope", "required")
        return envelope

    @property
    def supplier_token(self) -> SupplierToken:
        return self.envelope.assignment.supplier_token

    @property
    def invitation(self) -> SupplierInvitationToken:
        return self.envelope.assignment.invitation

    @property
    def scoped_intent_id(self) -> IntentId:
        return self.envelope.assignment.scoped_intent_id

    @property
    def scoped_buyer_token(self) -> BuyerToken:
        return self.envelope.assignment.scoped_buyer_token

    @property
    def category(self) -> str:
        return _require_str(self._payload().get("category"), "category")

    @property
    def airport(self) -> str:
        location = _require_dict(self._payload().get("location"), "location")
        return _require_str(location.get("airportCode"), "airport")

    @property
    def currency(self) -> str:
        return _require_str(self._constraints().get("currency"), "currency")

    @property
    def covered(self) -> CoveredPreference:
        raw = _require_str(self._requirements().get("covered"), "covered")
        try:
            return CoveredPreference(raw)
        except ValueError:
            raise ApplicationError("covered", "invalid") from None

    @property
    def shuttle_max_minutes(self) -> int:
        try:
            return require_shuttle_minutes(
                self._requirements().get("shuttleMaxMinutes"), "shuttle_max_minutes"
            )
        except DomainInvariantError as exc:
            raise ApplicationError(exc.field, exc.code) from None

    @property
    def representable_add_ons(self) -> frozenset[AddOn]:
        accessibility = self._constraints().get("accessibility")
        if not isinstance(accessibility, list):
            raise ApplicationError("accessibility", "required")
        return frozenset(
            _REPRESENTABLE_ADD_ONS[item]
            for item in accessibility
            if isinstance(item, str) and item in _REPRESENTABLE_ADD_ONS
        )

    @property
    def vehicle_class(self) -> str:
        return _require_str(self._requirements().get("vehicleClass"), "vehicleClass")

    @property
    def response_deadline(self) -> datetime:
        solicitation = _require_dict(self._payload().get("solicitation"), "solicitation")
        try:
            return parse_utc(solicitation.get("responseDeadline"), "responseDeadline")
        except DomainInvariantError as exc:
            raise ApplicationError(exc.field, exc.code) from None

    @property
    def envelope_expires_at(self) -> datetime:
        return self.envelope.assignment.valid_until

    @property
    def payload_expires_at(self) -> datetime:
        try:
            return parse_utc(self._payload().get("expiresAt"), "expiresAt")
        except DomainInvariantError as exc:
            raise ApplicationError(exc.field, exc.code) from None

    @property
    def disclosure_profile(self) -> str:
        return _require_str(self._disclosure().get("profile"), "disclosure")

    @property
    def disclosure_hash(self) -> PayloadHash:
        try:
            return PayloadHash(
                _require_str(self._disclosure().get("approvedPayloadHash"), "disclosure")
            )
        except DomainInvariantError as exc:
            raise ApplicationError(exc.field, exc.code) from None

    def _payload(self) -> dict[str, object]:
        return self.envelope.payload_dict()

    def _requirements(self) -> dict[str, object]:
        return _require_dict(self._payload().get("requirements"), "requirements")

    def _constraints(self) -> dict[str, object]:
        return _require_dict(self._payload().get("constraints"), "constraints")

    def _disclosure(self) -> dict[str, object]:
        return _require_dict(self._payload().get("disclosure"), "disclosure")


@dataclass(frozen=True, slots=True, init=False)
class CollectedSupplierResponse:
    """Immutable collected terminal. Offer payloads require a sealed dispatch binding."""

    supplier_token: SupplierToken
    invitation: SupplierInvitationToken
    correlation_id: CorrelationId
    kind: TerminalKind
    reason: ClosedReason | None
    received_at: datetime
    payload: Mapping[str, object] | None
    completed_at: datetime | None
    binding: AuthorizedResponseBinding | None

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise ApplicationError("response", "sealed")

    @classmethod
    def seal(
        cls,
        *,
        supplier_token: SupplierToken,
        invitation: SupplierInvitationToken,
        correlation_id: CorrelationId,
        kind: TerminalKind,
        received_at: datetime,
        reason: ClosedReason | None = None,
        payload: object = None,
        completed_at: datetime | None = None,
        binding: AuthorizedResponseBinding | None = None,
    ) -> CollectedSupplierResponse:
        if type(supplier_token) is not SupplierToken:
            raise ApplicationError("supplier_token", "invalid_opaque_syntax")
        if type(invitation) is not SupplierInvitationToken:
            raise ApplicationError("invitation", "required")
        if type(correlation_id) is not CorrelationId:
            raise ApplicationError("correlation_id", "invalid_opaque_syntax")
        if type(kind) is not TerminalKind:
            raise ApplicationError("kind", "invalid_enum")
        received = require_utc(received_at, "received_at")
        provenance = None if completed_at is None else require_utc(completed_at, "completed_at")
        frozen: Mapping[str, object] | None
        if payload is None:
            frozen = None
        else:
            if not isinstance(payload, Mapping):
                raise ApplicationError("payload", "must_be_object")
            frozen_payload = freeze_payload(payload)
            if not isinstance(frozen_payload, Mapping):
                raise ApplicationError("payload", "must_be_object")
            frozen = frozen_payload
        if binding is not None:
            if type(binding) is not AuthorizedResponseBinding:
                raise ApplicationError("binding", "required")
            if binding.supplier_token != supplier_token:
                raise ApplicationError("supplier_token", "mismatch")
            if binding.invitation != invitation:
                raise ApplicationError("invitation", "wrong_channel")
            if binding.correlation_id != correlation_id:
                raise ApplicationError("correlation_id", "mismatch")
        if kind is TerminalKind.OFFER:
            if binding is None:
                raise ApplicationError("binding", "required")
            if frozen is None or reason is not None:
                raise ApplicationError("payload", "offer_required")
        else:
            if frozen is not None:
                raise ApplicationError("payload", "must_be_absent")
            if reason is None:
                raise ApplicationError("reason", "required")
            if type(reason) is not ClosedReason:
                raise ApplicationError("reason", "invalid_enum")
        self = object.__new__(cls)
        object.__setattr__(self, "supplier_token", supplier_token)
        object.__setattr__(self, "invitation", invitation)
        object.__setattr__(self, "correlation_id", correlation_id)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "received_at", received)
        object.__setattr__(self, "payload", frozen)
        object.__setattr__(self, "completed_at", provenance)
        object.__setattr__(self, "binding", binding)
        return self


@dataclass(frozen=True, slots=True)
class MappedOffer:
    offer: Offer
    ranking_input: RankingOffer
    need: RankingNeed


def accept_offer(
    response: CollectedSupplierResponse,
    policy: TrustedPolicyEvaluation,
    *,
    evaluated_at: datetime,
    seen_versions: frozenset[int] = frozenset(),
    actor: ActorRef | None = None,
) -> MappedOffer:
    if type(response) is not CollectedSupplierResponse:
        raise ApplicationError("response", "required")
    if type(policy) is not TrustedPolicyEvaluation:
        raise ApplicationError("policy", "required")
    if response.kind is not TerminalKind.OFFER:
        raise ApplicationError("kind", "not_offer")
    if response.payload is None or response.binding is None:
        raise ApplicationError("payload", "offer_required")
    binding = response.binding
    received = require_utc(response.received_at, "received_at")
    evaluated = require_utc(evaluated_at, "evaluated_at")
    if actor is None:
        actor = ActorRef(ActorType.SYSTEM, ActorId("ar_01k2m3n4p5q6r7s8t9v0w1x2s1"))
    if type(actor) is not ActorRef:
        raise ApplicationError("actor", "invalid")
    if type(seen_versions) is not frozenset:
        raise ApplicationError("seen_versions", "invalid")
    contract = _parse_contract(thaw_payload(response.payload))
    _bind(contract, binding, received, evaluated, seen_versions)
    _eligibility(contract, binding, policy)
    aggregate = _map_domain(contract, binding, received, actor)
    ranking = RankingOffer(
        offer_id=aggregate.offer_id,
        supplier_token=aggregate.supplier_token,
        version=Version(contract.version),
        total_minor=contract.price.totalMinor,
        currency=contract.price.currency,
        shuttle_minutes=contract.service.shuttleMinutes,
        distance_metres=contract.service.distanceMeters,
        lot_type=LotType(contract.service.lotType.value),
        add_ons=frozenset(AddOn(item.value) for item in contract.service.addOns),
        cancellation=CancellationTerm(contract.terms.cancellation.value),
        refund=RefundTerm(contract.terms.refund.value),
        valid_from=parse_utc(contract.validFrom, "valid_from"),
        valid_until=parse_utc(contract.validUntil, "valid_until"),
        evidence_types=frozenset(EvidenceType(item.type.value) for item in contract.evidence),
        availability=SimulatedAvailability(contract.service.availability.value),
        simulation=True,
    )
    need = RankingNeed(
        covered=binding.covered,
        representable_add_ons=binding.representable_add_ons,
        shuttle_max_minutes=binding.shuttle_max_minutes,
    )
    return MappedOffer(aggregate, ranking, need)


def _parse_contract(payload: object) -> ContractOffer:
    if not isinstance(payload, dict):
        raise ApplicationError("payload", "must_be_object")
    try:
        return ContractOffer.model_validate(payload)
    except ValidationError as exc:
        loc = exc.errors()[0].get("loc", ("payload",))
        field = "/".join(str(item) for item in loc) if loc else "payload"
        raise ApplicationError(field, "schema_invalid") from None


def _bind(
    contract: ContractOffer,
    binding: AuthorizedResponseBinding,
    received_at: datetime,
    evaluated_at: datetime,
    seen_versions: frozenset[int],
) -> None:
    if contract.supplierToken != binding.supplier_token.to_primitive():
        raise ApplicationError("supplierToken", "mismatch")
    if contract.intentId != binding.scoped_intent_id.to_primitive():
        raise ApplicationError("intentId", "mismatch")
    if contract.status.value != "submitted":
        raise ApplicationError("status", "unsupported")
    if contract.version in seen_versions:
        raise ApplicationError("version", "duplicate")
    if seen_versions and contract.version <= max(seen_versions):
        raise ApplicationError("version", "stale")
    if contract.simulation is not True:
        raise ApplicationError("simulation", "must_be_true")
    if contract.price.currency != binding.currency:
        raise ApplicationError("currency", "mismatch")
    expected = contract.price.subtotalMinor + contract.price.feesMinor + contract.price.taxMinor
    if expected != contract.price.totalMinor:
        raise ApplicationError("totalMinor", "must_equal_components")
    valid_from = parse_utc(contract.validFrom, "validFrom")
    valid_until = parse_utc(contract.validUntil, "validUntil")
    if valid_until <= valid_from:
        raise ApplicationError("validity", "end_must_follow_start")
    if valid_from > received_at:
        raise ApplicationError("validFrom", "future")
    if evaluated_at < valid_from:
        raise ApplicationError("validFrom", "not_yet_valid")
    if received_at >= binding.response_deadline:
        raise ApplicationError("responseDeadline", "after_deadline")
    if received_at >= binding.envelope_expires_at:
        raise ApplicationError("envelope", "expired")
    if evaluated_at >= valid_until:
        raise ApplicationError("validUntil", "expired")
    if binding.category != "airport_parking":
        raise ApplicationError("category", "unsupported")


def _eligibility(
    contract: ContractOffer,
    binding: AuthorizedResponseBinding,
    policy: TrustedPolicyEvaluation,
) -> None:
    if policy.supplier_token != binding.supplier_token:
        raise ApplicationError("policy", "supplier_mismatch")
    if policy.scoped_intent_id != binding.scoped_intent_id:
        raise ApplicationError("policy", "intent_mismatch")
    if binding.airport not in policy.airports:
        raise ApplicationError("airport", "unsupported")
    if binding.vehicle_class not in policy.vehicles:
        raise ApplicationError("vehicleClass", "unsupported")
    availability = SimulatedAvailability(contract.service.availability.value)
    if availability is SimulatedAvailability.UNAVAILABLE_SIMULATED:
        raise ApplicationError("availability", "unavailable")
    if availability not in policy.allowed_availability:
        raise ApplicationError("availability", "unsupported")
    if contract.service.shuttleMinutes > binding.shuttle_max_minutes:
        raise ApplicationError("shuttleMinutes", "exceeds_maximum")
    if LotType(contract.service.lotType.value) not in policy.lot_types:
        raise ApplicationError("lotType", "unsupported")
    add_ons = frozenset(AddOn(item.value) for item in contract.service.addOns)
    if not add_ons.issubset(policy.add_ons):
        raise ApplicationError("addOns", "unsupported")
    if contract.price.feesMinor != policy.fees_minor:
        raise ApplicationError("feesMinor", "mismatch")
    if contract.price.taxMinor != policy.tax_minor:
        raise ApplicationError("taxMinor", "mismatch")
    offered = {
        (EvidenceType(item.type.value), EvidenceRef(item.ref).to_primitive())
        for item in contract.evidence
    }
    trusted = {(item.evidence_type, item.ref.to_primitive()) for item in policy.evidence}
    if offered != trusted:
        raise ApplicationError("evidence", "mismatch")
    if (
        policy.billable_days > 0
        and policy.floor_minor_per_day > JS_SAFE_MAX // policy.billable_days
    ):
        raise ApplicationError("floor_minor_per_day", "overflow")
    floor = policy.floor_minor_per_day * policy.billable_days
    add_on_floor = policy.add_on_price_minor if add_ons else 0
    if contract.price.subtotalMinor < floor + add_on_floor:
        raise ApplicationError("subtotalMinor", "price_floor")
    valid_from = parse_utc(contract.validFrom, "validFrom")
    valid_until = parse_utc(contract.validUntil, "validUntil")
    if not validity_duration_in_bounds(
        valid_from,
        valid_until,
        minimum_seconds=policy.min_validity_seconds,
        maximum_seconds=policy.max_validity_seconds,
    ):
        raise ApplicationError("validity", "out_of_range")
    cancellation = CancellationTerm(contract.terms.cancellation.value)
    if cancellation not in policy.allowed_cancellations:
        raise ApplicationError("cancellation", "unsupported")
    refund = RefundTerm(contract.terms.refund.value)
    if refund not in policy.allowed_refunds:
        raise ApplicationError("refund", "unsupported")
    if (
        contract.terms.cancellation.value == "non_refundable"
        and contract.terms.refund.value != "none"
    ):
        raise ApplicationError("refund", "invalid_pair")
    if (
        contract.terms.cancellation.value != "non_refundable"
        and contract.terms.refund.value == "none"
    ):
        raise ApplicationError("refund", "invalid_pair")


def _map_domain(
    contract: ContractOffer,
    binding: AuthorizedResponseBinding,
    received_at: datetime,
    actor: ActorRef,
) -> Offer:
    terms = OfferTerms(
        price=OfferPrice(
            Money(contract.price.subtotalMinor, contract.price.currency),
            Money(contract.price.feesMinor, contract.price.currency),
            Money(contract.price.taxMinor, contract.price.currency),
            Money(contract.price.totalMinor, contract.price.currency),
        ),
        lot_type=LotType(contract.service.lotType.value),
        shuttle_minutes=contract.service.shuttleMinutes,
        distance_metres=contract.service.distanceMeters,
        availability=SimulatedAvailability(contract.service.availability.value),
        add_ons=tuple(AddOn(item.value) for item in contract.service.addOns),
        cancellation=CancellationTerm(contract.terms.cancellation.value),
        refund=RefundTerm(contract.terms.refund.value),
        validity=TimeWindow(
            parse_utc(contract.validFrom, "validFrom"),
            parse_utc(contract.validUntil, "validUntil"),
        ),
        evidence=tuple(
            OfferEvidence(EvidenceType(item.type.value), EvidenceRef(item.ref))
            for item in contract.evidence
        ),
        signature=SignatureHandle(contract.signature),
        simulation=True,
    )
    try:
        current = Offer.invite(
            offer_id=OfferId(contract.offerId),
            intent_id=IntentId(contract.intentId),
            supplier_token=SupplierToken(contract.supplierToken),
            created_at=received_at,
        )
        request = TransitionRequest(
            expected_revision=current.revision,
            occurred_at=received_at,
            actor=actor,
            correlation_id=binding.correlation_id,
        )
        current = current.begin_draft(request).aggregate
        request = TransitionRequest(
            expected_revision=current.revision,
            occurred_at=received_at,
            actor=actor,
            correlation_id=binding.correlation_id,
        )
        current = current.submit(request, terms).aggregate
        request = TransitionRequest(
            expected_revision=current.revision,
            occurred_at=received_at,
            actor=actor,
            correlation_id=binding.correlation_id,
        )
        current = current.validate(request).aggregate
        request = TransitionRequest(
            expected_revision=current.revision,
            occurred_at=received_at,
            actor=actor,
            correlation_id=binding.correlation_id,
        )
        current = current.mark_eligible(request).aggregate
    except (DomainInvariantError, ExpiredResourceError, ApplicationError) as exc:
        if isinstance(exc, ApplicationError):
            raise
        field = getattr(exc, "field", "offer")
        code = getattr(exc, "code", "mapping_failed")
        raise ApplicationError(str(field), str(code)) from None
    except Exception:
        raise ApplicationError("offer", "mapping_failed") from None
    if current.state is not OfferState.ELIGIBLE:
        raise ApplicationError("state", "not_eligible")
    return current
