from __future__ import annotations

from collections.abc import Mapping, Sequence

from helpers import (
    AUTHORIZATION_ID,
    CANCEL_REASON,
    CLOSE_REASON,
    COUNTER_OFFER_ID,
    DECISION_EXPIRES_AT,
    DECLINE_REASON,
    DISPATCH_APPROVAL_ID,
    IDEMPOTENCY_KEY,
    INTENT_EXPIRES_AT,
    OFFER_VALID_UNTIL,
    PAYLOAD_HASH,
    RECEIPT_EXPIRES_AT,
    RECEIPT_SIGNATURE,
    REJECT_REASON,
    SUPPLIER_TOKEN,
    USER_APPROVAL_ID,
    at_minutes,
    draft_intent,
    intent_in_state,
    invited_offer,
    make_acceptance,
    offer_in_state,
    parkdirect_terms,
    request_at,
    resubmitted_terms,
    transaction_in_state,
    usd,
)

from itaa_domain.events import DomainEvent
from itaa_domain.value_objects import (
    AuthorizationAction,
    TransactionDeclineReason,
    TransactionFailureReason,
    Version,
)

FORBIDDEN_EVENT_KEYS = {
    "email",
    "name",
    "phone",
    "address",
    "payment",
    "itinerary",
    "prompt",
    "preference",
    "preferences",
    "competitor",
    "password",
    "credential",
    "credentials",
    "raw",
    "content",
    "explanation",
    "ranking",
    "secret",
    "sharepayload",
    "rawcontext",
    "fullname",
    "card",
    "terms",
    "requirements",
    "disclosure",
    "receipt",
}


def _walk(value: object) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            lowered = str(key).lower().replace("_", "")
            assert lowered not in FORBIDDEN_EVENT_KEYS, key
            _walk(item)
        return
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        for item in value:
            _walk(item)


def _all_transition_events() -> list[DomainEvent]:
    events: list[DomainEvent] = []
    intent = draft_intent()
    confirmed = intent.confirm(request_at(at_minutes(1), intent.revision))
    events.append(confirmed.event)
    previewed = confirmed.aggregate.preview_disclosure(
        request_at(at_minutes(2), confirmed.aggregate.revision),
        PAYLOAD_HASH,
    )
    events.append(previewed.event)
    approved = previewed.aggregate.approve_dispatch(
        request_at(at_minutes(3), previewed.aggregate.revision),
        DISPATCH_APPROVAL_ID,
    )
    events.append(approved.event)
    dispatched = approved.aggregate.dispatch(request_at(at_minutes(4), approved.aggregate.revision))
    events.append(dispatched.event)
    events.append(
        dispatched.aggregate.close(
            request_at(at_minutes(5), dispatched.aggregate.revision),
            CLOSE_REASON,
        ).event
    )
    events.append(
        draft_intent().cancel(request_at(at_minutes(1), intent.revision), CANCEL_REASON).event
    )
    expired_intent = intent_in_state("APPROVED")
    events.append(
        expired_intent.expire(request_at(INTENT_EXPIRES_AT, expired_intent.revision)).event
    )

    invited = invited_offer()
    drafted = invited.begin_draft(request_at(at_minutes(1), invited.revision))
    events.append(drafted.event)
    submitted = drafted.aggregate.submit(
        request_at(at_minutes(2), drafted.aggregate.revision),
        parkdirect_terms(),
    )
    events.append(submitted.event)
    events.append(
        submitted.aggregate.validate(request_at(at_minutes(3), submitted.aggregate.revision)).event
    )
    events.append(
        submitted.aggregate.counter(
            request_at(at_minutes(3), submitted.aggregate.revision),
            COUNTER_OFFER_ID,
            submitted.aggregate.offer_version,
        ).event
    )
    events.append(
        submitted.aggregate.reject(
            request_at(at_minutes(3), submitted.aggregate.revision),
            REJECT_REASON,
        ).event
    )
    countered = offer_in_state("COUNTERED")
    events.append(
        countered.resubmit(
            request_at(countered.updated_at, countered.revision),
            resubmitted_terms(),
            Version(2),
        ).event
    )
    validated = offer_in_state("VALIDATED")
    events.append(
        validated.mark_eligible(request_at(validated.updated_at, validated.revision)).event
    )
    events.append(validated.expire(request_at(OFFER_VALID_UNTIL, validated.revision)).event)
    eligible = offer_in_state("ELIGIBLE")
    events.append(eligible.recommend(request_at(eligible.updated_at, eligible.revision)).event)
    events.append(
        eligible.accept(
            request_at(eligible.updated_at.replace(hour=18), eligible.revision),
            make_acceptance(offer=eligible),
        ).event
    )
    recommended = offer_in_state("RECOMMENDED")
    events.append(
        recommended.decline(
            request_at(recommended.updated_at, recommended.revision),
            DECLINE_REASON,
        ).event
    )

    idle = transaction_in_state("NOT_REQUESTED")
    pending = idle.request_from_acceptance(
        request_at(idle.updated_at.replace(hour=18), idle.revision),
        make_acceptance(offer=eligible),
        eligible,
    )
    events.append(pending.event)
    approval = transaction_in_state("ACCEPTANCE_PENDING").require_approval(
        request_at(transaction_in_state("ACCEPTANCE_PENDING").updated_at, Version(2)),
        action=AuthorizationAction.RESERVE_PARKING,
        amount=usd(11900),
        supplier_token=SUPPLIER_TOKEN,
        decision_expires_at=DECISION_EXPIRES_AT,
    )
    events.append(approval.event)
    required = transaction_in_state("APPROVAL_REQUIRED")
    events.append(
        required.authorize_simulated(
            request_at(required.updated_at, required.revision),
            authorization_id=AUTHORIZATION_ID,
            user_approval_id=USER_APPROVAL_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            signature=RECEIPT_SIGNATURE,
            expires_at=RECEIPT_EXPIRES_AT,
        ).event
    )
    events.append(
        required.decline(
            request_at(required.updated_at, required.revision),
            TransactionDeclineReason.APPROVAL_WITHHELD,
        ).event
    )
    events.append(required.expire(request_at(DECISION_EXPIRES_AT, required.revision)).event)
    events.append(
        required.fail(
            request_at(required.updated_at, required.revision),
            TransactionFailureReason.AUTHORIZATION_FAILED,
        ).event
    )
    return events


def test_every_accepted_transition_emits_one_typed_privacy_safe_event() -> None:
    events = _all_transition_events()
    assert len(events) == 24
    assert len({event.event_type for event in events}) == 24
    for event in events:
        primitive = event.to_primitive()
        _walk(primitive)
        assert primitive["resourceVersion"] == event.resource_version
        assert primitive["occurredAt"].endswith("Z")
        assert primitive["actorId"]
        assert primitive["reasonCode"]
        assert primitive["correlationId"]
        assert primitive["action"]
        assert primitive["targetState"]
        assert "@" not in str(primitive)
        assert "prompt" not in str(primitive).lower()
        assert "itinerary" not in str(primitive).lower()
