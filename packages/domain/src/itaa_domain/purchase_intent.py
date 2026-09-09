"""Purchase Intent aggregate and exhaustive state machine."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from itaa_domain.errors import DomainInvariantError, ExpiredResourceError
from itaa_domain.events import EventType, emit_domain_event
from itaa_domain.identifiers import ApprovalId, BuyerToken, IntentId, RequirementId
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
    CancellationReason,
    ClosureReason,
    PayloadHash,
    Version,
    format_utc,
    require_exact_enum,
    require_utc,
)


class PurchaseIntentState(StrEnum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    DISCLOSURE_PREVIEWED = "DISCLOSURE_PREVIEWED"
    APPROVED = "APPROVED"
    DISPATCHED = "DISPATCHED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class PurchaseIntentAction(StrEnum):
    CONFIRM = "confirm"
    CANCEL = "cancel"
    PREVIEW_DISCLOSURE = "preview_disclosure"
    APPROVE_DISPATCH = "approve_dispatch"
    DISPATCH = "dispatch"
    EXPIRE = "expire"
    CLOSE = "close"


PURCHASE_INTENT_TRANSITIONS: dict[
    tuple[PurchaseIntentState, PurchaseIntentAction], PurchaseIntentState
] = {
    (PurchaseIntentState.DRAFT, PurchaseIntentAction.CONFIRM): PurchaseIntentState.CONFIRMED,
    (PurchaseIntentState.DRAFT, PurchaseIntentAction.CANCEL): PurchaseIntentState.CANCELLED,
    (
        PurchaseIntentState.CONFIRMED,
        PurchaseIntentAction.PREVIEW_DISCLOSURE,
    ): PurchaseIntentState.DISCLOSURE_PREVIEWED,
    (PurchaseIntentState.CONFIRMED, PurchaseIntentAction.CANCEL): PurchaseIntentState.CANCELLED,
    (
        PurchaseIntentState.DISCLOSURE_PREVIEWED,
        PurchaseIntentAction.APPROVE_DISPATCH,
    ): PurchaseIntentState.APPROVED,
    (
        PurchaseIntentState.DISCLOSURE_PREVIEWED,
        PurchaseIntentAction.CANCEL,
    ): PurchaseIntentState.CANCELLED,
    (PurchaseIntentState.APPROVED, PurchaseIntentAction.DISPATCH): PurchaseIntentState.DISPATCHED,
    (PurchaseIntentState.APPROVED, PurchaseIntentAction.EXPIRE): PurchaseIntentState.EXPIRED,
    (PurchaseIntentState.APPROVED, PurchaseIntentAction.CANCEL): PurchaseIntentState.CANCELLED,
    (PurchaseIntentState.DISPATCHED, PurchaseIntentAction.CANCEL): PurchaseIntentState.CANCELLED,
    (PurchaseIntentState.DISPATCHED, PurchaseIntentAction.CLOSE): PurchaseIntentState.CLOSED,
}

PURCHASE_INTENT_TERMINAL = frozenset(
    {
        PurchaseIntentState.CLOSED,
        PurchaseIntentState.CANCELLED,
        PurchaseIntentState.EXPIRED,
    }
)
_PI_DUPLICATE_ACTIONS = frozenset(
    {
        PurchaseIntentAction.CANCEL.value,
        PurchaseIntentAction.EXPIRE.value,
        PurchaseIntentAction.CLOSE.value,
    }
)
_FORWARD_PRE_DISPATCH = frozenset(
    {
        PurchaseIntentAction.CONFIRM,
        PurchaseIntentAction.PREVIEW_DISCLOSURE,
        PurchaseIntentAction.APPROVE_DISPATCH,
        PurchaseIntentAction.DISPATCH,
    }
)
_PI_EVENT_TYPES = {
    PurchaseIntentAction.CONFIRM: EventType.PURCHASE_INTENT_CONFIRMED,
    PurchaseIntentAction.CANCEL: EventType.PURCHASE_INTENT_CANCELLED,
    PurchaseIntentAction.PREVIEW_DISCLOSURE: EventType.PURCHASE_INTENT_DISCLOSURE_PREVIEWED,
    PurchaseIntentAction.APPROVE_DISPATCH: EventType.PURCHASE_INTENT_APPROVED,
    PurchaseIntentAction.DISPATCH: EventType.PURCHASE_INTENT_DISPATCHED,
    PurchaseIntentAction.EXPIRE: EventType.PURCHASE_INTENT_EXPIRED,
    PurchaseIntentAction.CLOSE: EventType.PURCHASE_INTENT_CLOSED,
}
_PI_REASON_TYPES = {
    PurchaseIntentAction.CANCEL: CancellationReason,
    PurchaseIntentAction.CLOSE: ClosureReason,
}
_HASH_REQUIRED = frozenset(
    {
        PurchaseIntentState.DISCLOSURE_PREVIEWED,
        PurchaseIntentState.APPROVED,
        PurchaseIntentState.DISPATCHED,
        PurchaseIntentState.CLOSED,
        PurchaseIntentState.EXPIRED,
    }
)
_APPROVAL_REQUIRED = frozenset(
    {
        PurchaseIntentState.APPROVED,
        PurchaseIntentState.DISPATCHED,
        PurchaseIntentState.CLOSED,
        PurchaseIntentState.EXPIRED,
    }
)


@dataclass(frozen=True, slots=True)
class PurchaseIntent:
    intent_id: IntentId
    requirement_id: RequirementId
    buyer_token: BuyerToken
    state: PurchaseIntentState
    revision: Version
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    disclosure_payload_hash: PayloadHash | None = None
    dispatch_approval_id: ApprovalId | None = None

    def __post_init__(self) -> None:
        require_exact_enum(self.state, PurchaseIntentState, "state")
        created = require_utc(self.created_at, "created_at")
        updated = require_utc(self.updated_at, "updated_at")
        expires = require_utc(self.expires_at, "expires_at")
        if expires <= created:
            raise DomainInvariantError("expires_at", "must_follow_created_at")
        if updated < created:
            raise DomainInvariantError("updated_at", "must_not_precede_created_at")
        if self.state in _HASH_REQUIRED and self.disclosure_payload_hash is None:
            raise DomainInvariantError("disclosure_payload_hash", "required")
        if self.state in _APPROVAL_REQUIRED and self.dispatch_approval_id is None:
            raise DomainInvariantError("dispatch_approval_id", "required")
        if self.state is PurchaseIntentState.EXPIRED and updated < expires:
            raise DomainInvariantError("updated_at", "not_yet_expired")
        if self.state == PurchaseIntentState.DRAFT and self.revision != Version.initial():
            raise DomainInvariantError("revision", "draft_must_start_at_one")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "updated_at", updated)
        object.__setattr__(self, "expires_at", expires)

    @classmethod
    def draft(
        cls,
        *,
        intent_id: IntentId,
        requirement_id: RequirementId,
        buyer_token: BuyerToken,
        created_at: datetime,
        expires_at: datetime,
    ) -> PurchaseIntent:
        return cls(
            intent_id=intent_id,
            requirement_id=requirement_id,
            buyer_token=buyer_token,
            state=PurchaseIntentState.DRAFT,
            revision=Version.initial(),
            created_at=created_at,
            updated_at=created_at,
            expires_at=expires_at,
        )

    def permitted_actions(self) -> tuple[str, ...]:
        return permitted_actions(PURCHASE_INTENT_TRANSITIONS, self.state)

    def confirm(self, request: TransitionRequest) -> TransitionResult[PurchaseIntent]:
        return self._transition(PurchaseIntentAction.CONFIRM, request)

    def cancel(
        self,
        request: TransitionRequest,
        reason: CancellationReason,
    ) -> TransitionResult[PurchaseIntent]:
        return self._transition(PurchaseIntentAction.CANCEL, request, reason=reason)

    def preview_disclosure(
        self,
        request: TransitionRequest,
        payload_hash: PayloadHash,
    ) -> TransitionResult[PurchaseIntent]:
        return self._transition(
            PurchaseIntentAction.PREVIEW_DISCLOSURE,
            request,
            payload_hash=payload_hash,
        )

    def approve_dispatch(
        self,
        request: TransitionRequest,
        approval_id: ApprovalId,
    ) -> TransitionResult[PurchaseIntent]:
        return self._transition(
            PurchaseIntentAction.APPROVE_DISPATCH,
            request,
            approval_id=approval_id,
        )

    def dispatch(self, request: TransitionRequest) -> TransitionResult[PurchaseIntent]:
        return self._transition(PurchaseIntentAction.DISPATCH, request)

    def expire(self, request: TransitionRequest) -> TransitionResult[PurchaseIntent]:
        return self._transition(PurchaseIntentAction.EXPIRE, request)

    def close(
        self,
        request: TransitionRequest,
        reason: ClosureReason,
    ) -> TransitionResult[PurchaseIntent]:
        return self._transition(PurchaseIntentAction.CLOSE, request, reason=reason)

    def apply(
        self,
        action: PurchaseIntentAction,
        request: TransitionRequest,
        *,
        payload_hash: PayloadHash | None = None,
        approval_id: ApprovalId | None = None,
        reason: CancellationReason | ClosureReason | None = None,
    ) -> TransitionResult[PurchaseIntent]:
        return self._transition(
            action,
            request,
            payload_hash=payload_hash,
            approval_id=approval_id,
            reason=reason,
        )

    def to_primitive(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "intentId": self.intent_id.to_primitive(),
            "requirementId": self.requirement_id.to_primitive(),
            "buyerToken": self.buyer_token.to_primitive(),
            "state": self.state.value,
            "revision": self.revision.to_primitive(),
            "createdAt": format_utc(self.created_at),
            "updatedAt": format_utc(self.updated_at),
            "expiresAt": format_utc(self.expires_at),
        }
        if self.disclosure_payload_hash is not None:
            payload["disclosurePayloadHash"] = self.disclosure_payload_hash.to_primitive()
        if self.dispatch_approval_id is not None:
            payload["dispatchApprovalId"] = self.dispatch_approval_id.to_primitive()
        return payload

    def _transition(
        self,
        action: PurchaseIntentAction,
        request: TransitionRequest,
        *,
        payload_hash: PayloadHash | None = None,
        approval_id: ApprovalId | None = None,
        reason: CancellationReason | ClosureReason | None = None,
    ) -> TransitionResult[PurchaseIntent]:
        require_exact_enum(action, PurchaseIntentAction, "action")
        assert_revision(
            self.revision,
            request.expected_revision,
            "purchase_intent",
            self.intent_id.to_primitive(),
        )
        target = PURCHASE_INTENT_TRANSITIONS.get((self.state, action))
        if target is None:
            reject_illegal(
                resource_type="purchase_intent",
                resource_id=self.intent_id.to_primitive(),
                current_state=self.state.value,
                attempted_action=action.value,
                permitted=self.permitted_actions(),
                terminal=self.state in PURCHASE_INTENT_TERMINAL,
                duplicate_actions=_PI_DUPLICATE_ACTIONS,
            )
            raise AssertionError("unreachable")
        assert_monotonic(self.updated_at, request.occurred_at)
        if action in _FORWARD_PRE_DISPATCH and request.occurred_at >= self.expires_at:
            raise ExpiredResourceError(
                resource_type="purchase_intent",
                resource_id=self.intent_id.to_primitive(),
                expired_at=format_utc(self.expires_at),
            )
        next_hash = self.disclosure_payload_hash
        next_approval = self.dispatch_approval_id
        reason_code = require_action_reason(
            reason,
            _PI_REASON_TYPES.get(action),
            action_code=action.value,
        )
        if action is PurchaseIntentAction.PREVIEW_DISCLOSURE:
            if payload_hash is None:
                raise DomainInvariantError("disclosure_payload_hash", "required")
            next_hash = payload_hash
        if action is PurchaseIntentAction.APPROVE_DISPATCH:
            if approval_id is None:
                raise DomainInvariantError("dispatch_approval_id", "required")
            if next_hash is None:
                raise DomainInvariantError("disclosure_payload_hash", "required")
            next_approval = approval_id
        if action is PurchaseIntentAction.EXPIRE and request.occurred_at < self.expires_at:
            raise DomainInvariantError("expires_at", "not_yet_expired")
        updated = replace(
            self,
            state=target,
            revision=self.revision.next(),
            updated_at=request.occurred_at,
            disclosure_payload_hash=next_hash,
            dispatch_approval_id=next_approval,
        )
        event = emit_domain_event(
            event_type=_PI_EVENT_TYPES[action],
            resource_id=self.intent_id.to_primitive(),
            resource_version=updated.revision.value,
            occurred_at=request.occurred_at,
            actor_type=request.actor.category,
            actor_id=request.actor.actor_id.to_primitive(),
            reason_code=reason_code,
            correlation_id=request.correlation_id.to_primitive(),
            intent_id=self.intent_id.to_primitive(),
            approval_id=next_approval.to_primitive() if next_approval is not None else None,
            payload_hash=next_hash.to_primitive() if next_hash is not None else None,
        )
        return TransitionResult(updated, event)
