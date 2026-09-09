"""Shared synthetic fixtures for domain tests. No system clock or network."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from itaa_domain.acceptance import Acceptance
from itaa_domain.identifiers import (
    AcceptanceId,
    ActorId,
    ApprovalId,
    AuthorizationId,
    BuyerToken,
    CorrelationId,
    CounterOfferId,
    IdempotencyKey,
    IntentId,
    OfferId,
    RequirementId,
    SignatureHandle,
    SupplierToken,
)
from itaa_domain.offer import Offer, OfferEvidence, OfferPrice, OfferTerms
from itaa_domain.protocol import TransitionRequest
from itaa_domain.purchase_intent import PurchaseIntent
from itaa_domain.requirement import Requirement
from itaa_domain.transaction import Transaction
from itaa_domain.value_objects import (
    AccessibilityNeed,
    ActorRef,
    ActorType,
    AirportCode,
    CancellationReason,
    CancellationTerm,
    ClosureReason,
    CoveredPreference,
    DeclineReason,
    EvidenceRef,
    EvidenceType,
    LotType,
    Money,
    PayloadHash,
    RefundTerm,
    RejectionReason,
    SimulatedAvailability,
    TimeWindow,
    VehicleClass,
    Version,
)

UTC = UTC

INTENT_ID = IntentId("pi_01k2m3n4p5q6r7s8t9v0w1x2y3")
BUYER_TOKEN = BuyerToken("bs_01k2m3n4p5q6r7s8t9v0w1x2y4")
REQUIREMENT_ID = RequirementId("rq_01k2m3n4p5q6r7s8t9v0w1x2z1")
OFFER_ID = OfferId("of_01k2m3n4p5q6r7s8t9v0w1x2a1")
OFFER_ID_SKY = OfferId("of_01k2m3n4p5q6r7s8t9v0w1x2a2")
SUPPLIER_TOKEN = SupplierToken("sp_01k2m3n4p5q6r7s8t9v0w1x2b1")
SUPPLIER_TOKEN_SKY = SupplierToken("sp_01k2m3n4p5q6r7s8t9v0w1x2b2")
COUNTER_OFFER_ID = CounterOfferId("co_01k2m3n4p5q6r7s8t9v0w1x2c1")
ACCEPTANCE_ID = AcceptanceId("ac_01k2m3n4p5q6r7s8t9v0w1x2d1")
AUTHORIZATION_ID = AuthorizationId("ta_01k2m3n4p5q6r7s8t9v0w1x2e1")
DISPATCH_APPROVAL_ID = ApprovalId("ap_01k2m3n4p5q6r7s8t9v0w1x2f1")
USER_APPROVAL_ID = ApprovalId("ap_01k2m3n4p5q6r7s8t9v0w1x2f2")
IDEMPOTENCY_KEY = IdempotencyKey("ik_01k2m3n4p5q6r7s8t9v0w1x2g1")
SIGNATURE = SignatureHandle("sg_01k2m3n4p5q6r7s8t9v0w1x2h1")
RECEIPT_SIGNATURE = SignatureHandle("sg_01k2m3n4p5q6r7s8t9v0w1x2h5")
PAYLOAD_HASH = PayloadHash(
    "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
)
TERMS_HASH = PayloadHash("sha256:fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210")

CREATED_AT = datetime(2026, 8, 20, 15, 0, tzinfo=UTC)
INTENT_EXPIRES_AT = datetime(2026, 8, 22, 15, 0, tzinfo=UTC)
OFFER_VALID_FROM = datetime(2026, 8, 20, 16, 0, tzinfo=UTC)
OFFER_VALID_UNTIL = datetime(2026, 8, 21, 16, 0, tzinfo=UTC)
ACCEPTANCE_CREATED_AT = datetime(2026, 8, 20, 18, 0, tzinfo=UTC)
ACCEPTANCE_EXPIRES_AT = datetime(2026, 8, 21, 18, 0, tzinfo=UTC)
DECISION_EXPIRES_AT = datetime(2026, 8, 20, 19, 5, tzinfo=UTC)
RECEIPT_EXPIRES_AT = datetime(2026, 8, 20, 19, 5, tzinfo=UTC)

ACTOR = ActorRef(ActorType.BUYER, ActorId("ar_01k2m3n4p5q6r7s8t9v0w1x2k1"))
CORRELATION = CorrelationId("cr_01k2m3n4p5q6r7s8t9v0w1x2k2")
CANCEL_REASON = CancellationReason.BUYER_REVOKED
CLOSE_REASON = ClosureReason.COMPLETED
REJECT_REASON = RejectionReason.INELIGIBLE
DECLINE_REASON = DeclineReason.BUYER_DECLINED


def at_minutes(offset: int) -> datetime:
    return CREATED_AT + timedelta(minutes=offset)


def request_at(instant: datetime, revision: Version) -> TransitionRequest:
    return TransitionRequest(
        expected_revision=revision,
        occurred_at=instant,
        actor=ACTOR,
        correlation_id=CORRELATION,
    )


def usd(amount: int) -> Money:
    return Money(amount, "USD")


def parkdirect_price() -> OfferPrice:
    return OfferPrice(usd(9800), usd(1200), usd(900), usd(11900))


def parkdirect_terms(*, signature: SignatureHandle = SIGNATURE) -> OfferTerms:
    return OfferTerms(
        price=parkdirect_price(),
        lot_type=LotType.UNCOVERED,
        shuttle_minutes=15,
        distance_metres=2400,
        availability=SimulatedAvailability.CONFIRMED_SIMULATED,
        add_ons=(),
        cancellation=CancellationTerm.FREE_UNTIL_24H,
        refund=RefundTerm.ORIGINAL_METHOD,
        validity=TimeWindow(OFFER_VALID_FROM, OFFER_VALID_UNTIL),
        evidence=(
            OfferEvidence(EvidenceType.SUPPLIER_POLICY, EvidenceRef("policy.parkdirect.v1")),
        ),
        signature=signature,
        simulation=True,
    )


def resubmitted_terms() -> OfferTerms:
    return OfferTerms(
        price=OfferPrice(usd(11000), usd(1200), usd(900), usd(13100)),
        lot_type=LotType.UNCOVERED,
        shuttle_minutes=15,
        distance_metres=2400,
        availability=SimulatedAvailability.CONFIRMED_SIMULATED,
        add_ons=(),
        cancellation=CancellationTerm.FREE_UNTIL_24H,
        refund=RefundTerm.ORIGINAL_METHOD,
        validity=TimeWindow(OFFER_VALID_FROM, OFFER_VALID_UNTIL),
        evidence=(
            OfferEvidence(EvidenceType.SUPPLIER_POLICY, EvidenceRef("policy.parkdirect.v1")),
        ),
        signature=SignatureHandle("sg_01k2m3n4p5q6r7s8t9v0w1x2h4"),
        simulation=True,
    )


def make_requirement() -> Requirement:
    return Requirement.create(
        requirement_id=REQUIREMENT_ID,
        airport=AirportCode("JFK"),
        service_window=TimeWindow.from_primitives(
            "2026-09-03T13:00:00Z",
            "2026-09-08T22:00:00Z",
        ),
        vehicle_class=VehicleClass.STANDARD,
        covered=CoveredPreference.PREFERRED,
        shuttle_max_minutes=20,
        currency="USD",
        accessibility=(AccessibilityNeed.EV_CHARGING,),
        created_at=CREATED_AT,
    )


def draft_intent() -> PurchaseIntent:
    return PurchaseIntent.draft(
        intent_id=INTENT_ID,
        requirement_id=REQUIREMENT_ID,
        buyer_token=BUYER_TOKEN,
        created_at=CREATED_AT,
        expires_at=INTENT_EXPIRES_AT,
    )


def intent_in_state(state_name: str) -> PurchaseIntent:
    from itaa_domain.purchase_intent import PurchaseIntentState

    current = draft_intent()
    target = PurchaseIntentState(state_name)
    if target is PurchaseIntentState.DRAFT:
        return current
    current = current.confirm(request_at(at_minutes(1), current.revision)).aggregate
    if target is PurchaseIntentState.CONFIRMED:
        return current
    if target is PurchaseIntentState.CANCELLED:
        return current.cancel(request_at(at_minutes(2), current.revision), CANCEL_REASON).aggregate
    current = current.preview_disclosure(
        request_at(at_minutes(2), current.revision),
        PAYLOAD_HASH,
    ).aggregate
    if target is PurchaseIntentState.DISCLOSURE_PREVIEWED:
        return current
    current = current.approve_dispatch(
        request_at(at_minutes(3), current.revision),
        DISPATCH_APPROVAL_ID,
    ).aggregate
    if target is PurchaseIntentState.APPROVED:
        return current
    if target is PurchaseIntentState.EXPIRED:
        return current.expire(request_at(INTENT_EXPIRES_AT, current.revision)).aggregate
    current = current.dispatch(request_at(at_minutes(4), current.revision)).aggregate
    if target is PurchaseIntentState.DISPATCHED:
        return current
    if target is PurchaseIntentState.CLOSED:
        return current.close(request_at(at_minutes(5), current.revision), CLOSE_REASON).aggregate
    raise AssertionError(f"unsupported intent state {state_name}")


def invited_offer() -> Offer:
    return Offer.invite(
        offer_id=OFFER_ID,
        intent_id=INTENT_ID,
        supplier_token=SUPPLIER_TOKEN,
        created_at=CREATED_AT,
    )


def make_acceptance(*, offer: Offer | None = None, offer_id: OfferId = OFFER_ID) -> Acceptance:
    version = offer.offer_version if offer is not None else Version.initial()
    bound_id = offer.offer_id if offer is not None else offer_id
    return Acceptance.record(
        acceptance_id=ACCEPTANCE_ID,
        intent_id=INTENT_ID,
        offer_id=bound_id,
        offer_version=version,
        accepted_terms_hash=TERMS_HASH,
        buyer_approval_id=USER_APPROVAL_ID,
        created_at=ACCEPTANCE_CREATED_AT,
        expires_at=ACCEPTANCE_EXPIRES_AT,
    )


def offer_in_state(state_name: str) -> Offer:
    from itaa_domain.offer import OfferState

    current = invited_offer()
    target = OfferState(state_name)
    if target is OfferState.INVITED:
        return current
    current = current.begin_draft(request_at(at_minutes(1), current.revision)).aggregate
    if target is OfferState.DRAFT:
        return current
    current = current.submit(
        request_at(at_minutes(2), current.revision),
        parkdirect_terms(),
    ).aggregate
    if target is OfferState.SUBMITTED:
        return current
    if target is OfferState.COUNTERED:
        return current.counter(
            request_at(at_minutes(3), current.revision),
            COUNTER_OFFER_ID,
            current.offer_version,
        ).aggregate
    if target is OfferState.REJECTED:
        return current.reject(
            request_at(at_minutes(3), current.revision),
            REJECT_REASON,
        ).aggregate
    current = current.validate(request_at(at_minutes(3), current.revision)).aggregate
    if target is OfferState.VALIDATED:
        return current
    if target is OfferState.EXPIRED:
        return current.expire(request_at(OFFER_VALID_UNTIL, current.revision)).aggregate
    current = current.mark_eligible(request_at(at_minutes(4), current.revision)).aggregate
    if target is OfferState.ELIGIBLE:
        return current
    current = current.recommend(request_at(at_minutes(5), current.revision)).aggregate
    if target is OfferState.RECOMMENDED:
        return current
    if target is OfferState.ACCEPTED:
        return current.accept(
            request_at(ACCEPTANCE_CREATED_AT, current.revision),
            make_acceptance(offer=current),
        ).aggregate
    if target is OfferState.DECLINED:
        return current.decline(
            request_at(at_minutes(6), current.revision),
            DECLINE_REASON,
        ).aggregate
    raise AssertionError(f"unsupported offer state {state_name}")


def idle_transaction() -> Transaction:
    return Transaction.not_requested(CREATED_AT)


def transaction_in_state(state_name: str) -> Transaction:
    from itaa_domain.transaction import TransactionState
    from itaa_domain.value_objects import (
        AuthorizationAction,
        TransactionDeclineReason,
        TransactionFailureReason,
    )

    offer = offer_in_state("ELIGIBLE")
    acceptance = make_acceptance(offer=offer)
    current = idle_transaction()
    target = TransactionState(state_name)
    if target is TransactionState.NOT_REQUESTED:
        return current
    current = current.request_from_acceptance(
        request_at(ACCEPTANCE_CREATED_AT, current.revision),
        acceptance,
        offer,
    ).aggregate
    if target is TransactionState.ACCEPTANCE_PENDING:
        return current
    current = current.require_approval(
        request_at(at_minutes(181), current.revision),
        action=AuthorizationAction.RESERVE_PARKING,
        amount=usd(11900),
        supplier_token=SUPPLIER_TOKEN,
        decision_expires_at=DECISION_EXPIRES_AT,
    ).aggregate
    if target is TransactionState.APPROVAL_REQUIRED:
        return current
    if target is TransactionState.DECLINED:
        return current.decline(
            request_at(at_minutes(182), current.revision),
            TransactionDeclineReason.APPROVAL_WITHHELD,
        ).aggregate
    if target is TransactionState.FAILED:
        return current.fail(
            request_at(at_minutes(182), current.revision),
            TransactionFailureReason.AUTHORIZATION_FAILED,
        ).aggregate
    if target is TransactionState.EXPIRED:
        return current.expire(request_at(DECISION_EXPIRES_AT, current.revision)).aggregate
    if target is TransactionState.AUTHORIZED_SIMULATED:
        return current.authorize_simulated(
            request_at(at_minutes(182), current.revision),
            authorization_id=AUTHORIZATION_ID,
            user_approval_id=USER_APPROVAL_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            signature=RECEIPT_SIGNATURE,
            expires_at=RECEIPT_EXPIRES_AT,
        ).aggregate
    raise AssertionError(f"unsupported transaction state {state_name}")
