"""Simulated transaction authorization state machine."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from itaa_domain.acceptance import Acceptance
from itaa_domain.errors import DomainInvariantError, ExpiredResourceError, OfferVersionMismatchError
from itaa_domain.events import EventType, emit_domain_event
from itaa_domain.identifiers import (
    UNBOUND_TRANSACTION_ID,
    AcceptanceId,
    ApprovalId,
    AuthorizationId,
    IdempotencyKey,
    SignatureHandle,
    SupplierToken,
)
from itaa_domain.offer import Offer
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
    AuthorizationAction,
    AuthorizationMode,
    Money,
    TransactionDeclineReason,
    TransactionFailureReason,
    Version,
    format_utc,
    require_exact_enum,
    require_utc,
)


class TransactionState(StrEnum):
    NOT_REQUESTED = "NOT_REQUESTED"
    ACCEPTANCE_PENDING = "ACCEPTANCE_PENDING"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    AUTHORIZED_SIMULATED = "AUTHORIZED_SIMULATED"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


class TransactionAction(StrEnum):
    REQUEST_FROM_ACCEPTANCE = "request_from_acceptance"
    REQUIRE_APPROVAL = "require_approval"
    AUTHORIZE_SIMULATED = "authorize_simulated"
    DECLINE = "decline"
    EXPIRE = "expire"
    FAIL = "fail"


TRANSACTION_TRANSITIONS: dict[tuple[TransactionState, TransactionAction], TransactionState] = {
    (
        TransactionState.NOT_REQUESTED,
        TransactionAction.REQUEST_FROM_ACCEPTANCE,
    ): TransactionState.ACCEPTANCE_PENDING,
    (
        TransactionState.ACCEPTANCE_PENDING,
        TransactionAction.REQUIRE_APPROVAL,
    ): TransactionState.APPROVAL_REQUIRED,
    (
        TransactionState.APPROVAL_REQUIRED,
        TransactionAction.AUTHORIZE_SIMULATED,
    ): TransactionState.AUTHORIZED_SIMULATED,
    (TransactionState.APPROVAL_REQUIRED, TransactionAction.DECLINE): TransactionState.DECLINED,
    (TransactionState.APPROVAL_REQUIRED, TransactionAction.EXPIRE): TransactionState.EXPIRED,
    (TransactionState.APPROVAL_REQUIRED, TransactionAction.FAIL): TransactionState.FAILED,
}

TRANSACTION_TERMINAL = frozenset(
    {
        TransactionState.AUTHORIZED_SIMULATED,
        TransactionState.DECLINED,
        TransactionState.EXPIRED,
        TransactionState.FAILED,
    }
)
_TX_DUPLICATE_ACTIONS = frozenset(
    {
        TransactionAction.AUTHORIZE_SIMULATED.value,
        TransactionAction.DECLINE.value,
        TransactionAction.EXPIRE.value,
        TransactionAction.FAIL.value,
    }
)
_TX_EVENT_TYPES = {
    TransactionAction.REQUEST_FROM_ACCEPTANCE: EventType.TRANSACTION_REQUESTED,
    TransactionAction.REQUIRE_APPROVAL: EventType.TRANSACTION_APPROVAL_REQUIRED,
    TransactionAction.AUTHORIZE_SIMULATED: EventType.TRANSACTION_AUTHORIZED_SIMULATED,
    TransactionAction.DECLINE: EventType.TRANSACTION_DECLINED,
    TransactionAction.EXPIRE: EventType.TRANSACTION_EXPIRED,
    TransactionAction.FAIL: EventType.TRANSACTION_FAILED,
}
_TX_REASON_TYPES = {
    TransactionAction.DECLINE: TransactionDeclineReason,
    TransactionAction.FAIL: TransactionFailureReason,
}


@dataclass(frozen=True, slots=True)
class AuthorizationReceipt:
    authorization_id: AuthorizationId
    acceptance_id: AcceptanceId
    action: AuthorizationAction
    amount: Money
    supplier_token: SupplierToken
    mode: AuthorizationMode
    idempotency_key: IdempotencyKey
    user_approval_id: ApprovalId
    authorized_at: datetime
    expires_at: datetime
    signature: SignatureHandle

    def __post_init__(self) -> None:
        if self.action is not AuthorizationAction.RESERVE_PARKING:
            raise DomainInvariantError("action", "must_be_reserve_parking")
        if self.mode is not AuthorizationMode.SIMULATED:
            raise DomainInvariantError("mode", "must_be_simulated")
        authorized = require_utc(self.authorized_at, "authorized_at")
        expires = require_utc(self.expires_at, "expires_at")
        if expires <= authorized:
            raise DomainInvariantError("expires_at", "must_follow_authorized_at")
        object.__setattr__(self, "authorized_at", authorized)
        object.__setattr__(self, "expires_at", expires)

    def to_primitive(self) -> dict[str, object]:
        return {
            "authorizationId": self.authorization_id.to_primitive(),
            "acceptanceId": self.acceptance_id.to_primitive(),
            "action": self.action.value,
            "amountMinor": self.amount.amount_minor,
            "currency": self.amount.currency,
            "supplierToken": self.supplier_token.to_primitive(),
            "mode": self.mode.value,
            "idempotencyKey": self.idempotency_key.to_primitive(),
            "userApprovalId": self.user_approval_id.to_primitive(),
            "authorizedAt": format_utc(self.authorized_at),
            "expiresAt": format_utc(self.expires_at),
            "receiptSignature": self.signature.to_primitive(),
        }


@dataclass(frozen=True, slots=True)
class Transaction:
    state: TransactionState
    revision: Version
    created_at: datetime
    updated_at: datetime
    acceptance: Acceptance | None = None
    action: AuthorizationAction | None = None
    amount: Money | None = None
    supplier_token: SupplierToken | None = None
    decision_expires_at: datetime | None = None
    receipt: AuthorizationReceipt | None = None

    def __post_init__(self) -> None:
        require_exact_enum(self.state, TransactionState, "state")
        created = require_utc(self.created_at, "created_at")
        updated = require_utc(self.updated_at, "updated_at")
        if updated < created:
            raise DomainInvariantError("updated_at", "must_not_precede_created_at")
        if self.action is not None and self.action is not AuthorizationAction.RESERVE_PARKING:
            raise DomainInvariantError("action", "must_be_reserve_parking")
        deadline = self.decision_expires_at
        if deadline is not None:
            deadline = require_utc(deadline, "decision_expires_at")
            object.__setattr__(self, "decision_expires_at", deadline)
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "updated_at", updated)
        self._assert_state_invariants()

    def _assert_state_invariants(self) -> None:
        if self.state is TransactionState.NOT_REQUESTED:
            if self.revision != Version.initial():
                raise DomainInvariantError("revision", "not_requested_must_start_at_one")
            self._forbid_fields(
                acceptance=self.acceptance,
                action=self.action,
                amount=self.amount,
                supplier_token=self.supplier_token,
                decision_expires_at=self.decision_expires_at,
                receipt=self.receipt,
            )
            return
        if self.acceptance is None:
            raise DomainInvariantError("acceptance", "required")
        if (
            self.acceptance.is_expired_at(self.updated_at)
            and self.state is TransactionState.ACCEPTANCE_PENDING
        ):
            raise DomainInvariantError("acceptance", "expired")
        if self.state is TransactionState.ACCEPTANCE_PENDING:
            self._forbid_fields(
                action=self.action,
                amount=self.amount,
                supplier_token=self.supplier_token,
                decision_expires_at=self.decision_expires_at,
                receipt=self.receipt,
            )
            return
        if self.action is None or self.amount is None or self.supplier_token is None:
            raise DomainInvariantError("approval_request", "required")
        if self.action is not AuthorizationAction.RESERVE_PARKING:
            raise DomainInvariantError("action", "must_be_reserve_parking")
        if self.decision_expires_at is None:
            raise DomainInvariantError("decision_expires_at", "required")
        if self.decision_expires_at > self.acceptance.expires_at:
            raise DomainInvariantError("decision_expires_at", "exceeds_acceptance_expiry")
        if self.state is TransactionState.APPROVAL_REQUIRED:
            if self.decision_expires_at <= self.updated_at:
                raise DomainInvariantError("decision_expires_at", "must_be_future")
            if self.receipt is not None:
                raise DomainInvariantError("receipt", "must_be_absent")
            return
        if self.state is TransactionState.AUTHORIZED_SIMULATED:
            if self.receipt is None:
                raise DomainInvariantError("receipt", "required")
            self._assert_receipt_matches()
            deadline = self.decision_expires_at
            acceptance = self.acceptance
            if deadline is None:
                raise DomainInvariantError("decision_expires_at", "required")
            if acceptance is None:
                raise DomainInvariantError("acceptance", "required")
            if self.updated_at >= deadline:
                raise DomainInvariantError("updated_at", "past_decision_deadline")
            if acceptance.is_expired_at(self.updated_at):
                raise DomainInvariantError("updated_at", "acceptance_expired")
            return
        if self.state in {TransactionState.DECLINED, TransactionState.FAILED}:
            if self.receipt is not None:
                raise DomainInvariantError("receipt", "must_be_absent")
            return
        if self.state is TransactionState.EXPIRED:
            if self.receipt is not None:
                raise DomainInvariantError("receipt", "must_be_absent")
            deadline = self.decision_expires_at
            if deadline is None:
                raise DomainInvariantError("decision_expires_at", "required")
            if self.updated_at < deadline:
                raise DomainInvariantError("updated_at", "not_yet_expired")
            return
        raise DomainInvariantError("state", "unsupported")

    def _forbid_fields(self, **fields: object) -> None:
        for name, value in fields.items():
            if value is not None:
                raise DomainInvariantError(name, "must_be_absent")

    def _assert_receipt_matches(self) -> None:
        receipt = self.receipt
        if (
            receipt is None
            or self.acceptance is None
            or self.amount is None
            or self.supplier_token is None
        ):
            raise DomainInvariantError("receipt", "required")
        if receipt.mode is not AuthorizationMode.SIMULATED:
            raise DomainInvariantError("mode", "must_be_simulated")
        if receipt.acceptance_id != self.acceptance.acceptance_id:
            raise DomainInvariantError("acceptance_id", "mismatch")
        if receipt.action != self.action:
            raise DomainInvariantError("action", "mismatch")
        if receipt.amount != self.amount:
            raise DomainInvariantError("amount", "mismatch")
        if receipt.supplier_token != self.supplier_token:
            raise DomainInvariantError("supplier_token", "mismatch")
        if receipt.authorized_at != self.updated_at:
            raise DomainInvariantError("authorized_at", "mismatch")

    @classmethod
    def not_requested(cls, created_at: datetime) -> Transaction:
        return cls(
            state=TransactionState.NOT_REQUESTED,
            revision=Version.initial(),
            created_at=created_at,
            updated_at=created_at,
        )

    @property
    def resource_id(self) -> str:
        if self.acceptance is None:
            return UNBOUND_TRANSACTION_ID
        return self.acceptance.acceptance_id.to_primitive()

    def permitted_actions(self) -> tuple[str, ...]:
        return permitted_actions(TRANSACTION_TRANSITIONS, self.state)

    def request_from_acceptance(
        self,
        request: TransitionRequest,
        acceptance: Acceptance,
        offer: Offer,
    ) -> TransitionResult[Transaction]:
        return self._transition(
            TransactionAction.REQUEST_FROM_ACCEPTANCE,
            request,
            acceptance=acceptance,
            offer=offer,
        )

    def require_approval(
        self,
        request: TransitionRequest,
        *,
        action: AuthorizationAction,
        amount: Money,
        supplier_token: SupplierToken,
        decision_expires_at: datetime,
    ) -> TransitionResult[Transaction]:
        return self._transition(
            TransactionAction.REQUIRE_APPROVAL,
            request,
            authorization_action=action,
            amount=amount,
            supplier_token=supplier_token,
            decision_expires_at=decision_expires_at,
        )

    def authorize_simulated(
        self,
        request: TransitionRequest,
        *,
        authorization_id: AuthorizationId,
        user_approval_id: ApprovalId,
        idempotency_key: IdempotencyKey,
        signature: SignatureHandle,
        expires_at: datetime,
    ) -> TransitionResult[Transaction]:
        return self._transition(
            TransactionAction.AUTHORIZE_SIMULATED,
            request,
            authorization_id=authorization_id,
            user_approval_id=user_approval_id,
            idempotency_key=idempotency_key,
            signature=signature,
            receipt_expires_at=expires_at,
        )

    def decline(
        self,
        request: TransitionRequest,
        reason: TransactionDeclineReason,
    ) -> TransitionResult[Transaction]:
        return self._transition(TransactionAction.DECLINE, request, reason=reason)

    def expire(self, request: TransitionRequest) -> TransitionResult[Transaction]:
        return self._transition(TransactionAction.EXPIRE, request)

    def fail(
        self,
        request: TransitionRequest,
        reason: TransactionFailureReason,
    ) -> TransitionResult[Transaction]:
        return self._transition(TransactionAction.FAIL, request, reason=reason)

    def apply(
        self,
        action: TransactionAction,
        request: TransitionRequest,
        *,
        acceptance: Acceptance | None = None,
        offer: Offer | None = None,
        authorization_action: AuthorizationAction | None = None,
        amount: Money | None = None,
        supplier_token: SupplierToken | None = None,
        decision_expires_at: datetime | None = None,
        authorization_id: AuthorizationId | None = None,
        user_approval_id: ApprovalId | None = None,
        idempotency_key: IdempotencyKey | None = None,
        signature: SignatureHandle | None = None,
        receipt_expires_at: datetime | None = None,
        reason: TransactionDeclineReason | TransactionFailureReason | None = None,
    ) -> TransitionResult[Transaction]:
        return self._transition(
            action,
            request,
            acceptance=acceptance,
            offer=offer,
            authorization_action=authorization_action,
            amount=amount,
            supplier_token=supplier_token,
            decision_expires_at=decision_expires_at,
            authorization_id=authorization_id,
            user_approval_id=user_approval_id,
            idempotency_key=idempotency_key,
            signature=signature,
            receipt_expires_at=receipt_expires_at,
            reason=reason,
        )

    def to_primitive(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "state": self.state.value,
            "revision": self.revision.to_primitive(),
            "createdAt": format_utc(self.created_at),
            "updatedAt": format_utc(self.updated_at),
            "resourceId": self.resource_id,
        }
        if self.acceptance is not None:
            payload["acceptanceId"] = self.acceptance.acceptance_id.to_primitive()
        if self.action is not None:
            payload["action"] = self.action.value
        if self.amount is not None:
            payload["amount"] = self.amount.to_primitive()
        if self.supplier_token is not None:
            payload["supplierToken"] = self.supplier_token.to_primitive()
        if self.decision_expires_at is not None:
            payload["decisionExpiresAt"] = format_utc(self.decision_expires_at)
        if self.receipt is not None:
            payload["receipt"] = self.receipt.to_primitive()
        return payload

    def _transition(
        self,
        action: TransactionAction,
        request: TransitionRequest,
        *,
        acceptance: Acceptance | None = None,
        offer: Offer | None = None,
        authorization_action: AuthorizationAction | None = None,
        amount: Money | None = None,
        supplier_token: SupplierToken | None = None,
        decision_expires_at: datetime | None = None,
        authorization_id: AuthorizationId | None = None,
        user_approval_id: ApprovalId | None = None,
        idempotency_key: IdempotencyKey | None = None,
        signature: SignatureHandle | None = None,
        receipt_expires_at: datetime | None = None,
        reason: TransactionDeclineReason | TransactionFailureReason | None = None,
    ) -> TransitionResult[Transaction]:
        require_exact_enum(action, TransactionAction, "action")
        assert_revision(self.revision, request.expected_revision, "transaction", self.resource_id)
        target = TRANSACTION_TRANSITIONS.get((self.state, action))
        if target is None:
            reject_illegal(
                resource_type="transaction",
                resource_id=self.resource_id,
                current_state=self.state.value,
                attempted_action=action.value,
                permitted=self.permitted_actions(),
                terminal=self.state in TRANSACTION_TERMINAL,
                duplicate_actions=_TX_DUPLICATE_ACTIONS,
            )
            raise AssertionError("unreachable")
        assert_monotonic(self.updated_at, request.occurred_at)
        next_acceptance = self.acceptance
        next_action = self.action
        next_amount = self.amount
        next_supplier = self.supplier_token
        next_decision_expiry = self.decision_expires_at
        next_receipt = self.receipt
        reason_code = require_action_reason(
            reason,
            _TX_REASON_TYPES.get(action),
            action_code=action.value,
        )
        if action is TransactionAction.REQUEST_FROM_ACCEPTANCE:
            if acceptance is None or offer is None:
                raise DomainInvariantError("acceptance", "required")
            if acceptance.is_expired_at(request.occurred_at):
                raise ExpiredResourceError(
                    resource_type="acceptance",
                    resource_id=acceptance.acceptance_id.to_primitive(),
                    expired_at=format_utc(acceptance.expires_at),
                )
            if acceptance.offer_id != offer.offer_id:
                raise DomainInvariantError("offer_id", "mismatch")
            if acceptance.intent_id != offer.intent_id:
                raise DomainInvariantError("intent_id", "mismatch")
            if acceptance.offer_version != offer.offer_version:
                raise OfferVersionMismatchError(
                    offer_id=offer.offer_id.to_primitive(),
                    expected_version=offer.offer_version.value,
                    actual_version=acceptance.offer_version.value,
                )
            next_acceptance = acceptance
        if action is TransactionAction.REQUIRE_APPROVAL:
            if (
                authorization_action is None
                or amount is None
                or supplier_token is None
                or decision_expires_at is None
            ):
                raise DomainInvariantError("approval_request", "required")
            if authorization_action is not AuthorizationAction.RESERVE_PARKING:
                raise DomainInvariantError("action", "must_be_reserve_parking")
            next_action = authorization_action
            next_amount = amount
            next_supplier = supplier_token
            next_decision_expiry = require_utc(decision_expires_at, "decision_expires_at")
            if next_decision_expiry <= request.occurred_at:
                raise DomainInvariantError("decision_expires_at", "must_be_future")
            if next_acceptance is not None and next_decision_expiry > next_acceptance.expires_at:
                raise DomainInvariantError("decision_expires_at", "exceeds_acceptance_expiry")
        if action is TransactionAction.AUTHORIZE_SIMULATED:
            if (
                authorization_id is None
                or user_approval_id is None
                or idempotency_key is None
                or signature is None
                or receipt_expires_at is None
            ):
                raise DomainInvariantError("authorization", "required")
            if next_acceptance is None or next_amount is None or next_supplier is None:
                raise DomainInvariantError("approval_request", "required")
            if next_decision_expiry is None:
                raise DomainInvariantError("decision_expires_at", "required")
            if request.occurred_at >= next_decision_expiry:
                raise ExpiredResourceError(
                    resource_type="transaction",
                    resource_id=self.resource_id,
                    expired_at=format_utc(next_decision_expiry),
                )
            if next_acceptance.is_expired_at(request.occurred_at):
                raise ExpiredResourceError(
                    resource_type="acceptance",
                    resource_id=next_acceptance.acceptance_id.to_primitive(),
                    expired_at=format_utc(next_acceptance.expires_at),
                )
            if amount is not None and amount != next_amount:
                raise DomainInvariantError("amount", "substitution_forbidden")
            if supplier_token is not None and supplier_token != next_supplier:
                raise DomainInvariantError("supplier_token", "substitution_forbidden")
            next_receipt = AuthorizationReceipt(
                authorization_id=authorization_id,
                acceptance_id=next_acceptance.acceptance_id,
                action=AuthorizationAction.RESERVE_PARKING,
                amount=next_amount,
                supplier_token=next_supplier,
                mode=AuthorizationMode.SIMULATED,
                idempotency_key=idempotency_key,
                user_approval_id=user_approval_id,
                authorized_at=request.occurred_at,
                expires_at=receipt_expires_at,
                signature=signature,
            )
        if action is TransactionAction.EXPIRE and next_decision_expiry is None:
            raise DomainInvariantError("decision_expires_at", "required")
        if (
            action is TransactionAction.EXPIRE
            and next_decision_expiry is not None
            and request.occurred_at < next_decision_expiry
        ):
            raise DomainInvariantError("decision_expires_at", "not_yet_expired")
        updated = replace(
            self,
            state=target,
            revision=self.revision.next(),
            updated_at=request.occurred_at,
            acceptance=next_acceptance,
            action=next_action,
            amount=next_amount,
            supplier_token=next_supplier,
            decision_expires_at=next_decision_expiry,
            receipt=next_receipt,
        )
        event = emit_domain_event(
            event_type=_TX_EVENT_TYPES[action],
            resource_id=updated.resource_id,
            resource_version=updated.revision.value,
            occurred_at=request.occurred_at,
            actor_type=request.actor.category,
            actor_id=request.actor.actor_id.to_primitive(),
            reason_code=reason_code,
            correlation_id=request.correlation_id.to_primitive(),
            acceptance_id=(
                updated.acceptance.acceptance_id.to_primitive()
                if updated.acceptance is not None
                else None
            ),
            offer_id=(
                updated.acceptance.offer_id.to_primitive()
                if updated.acceptance is not None
                else None
            ),
            intent_id=(
                updated.acceptance.intent_id.to_primitive()
                if updated.acceptance is not None
                else None
            ),
            approval_id=user_approval_id.to_primitive() if user_approval_id is not None else None,
            authorization_id=(
                next_receipt.authorization_id.to_primitive() if next_receipt is not None else None
            ),
            idempotency_key=(
                idempotency_key.to_primitive() if idempotency_key is not None else None
            ),
            simulation=True,
        )
        return TransitionResult(updated, event)
