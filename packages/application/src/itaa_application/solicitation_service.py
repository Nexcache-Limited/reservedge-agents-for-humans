"""Isolation-safe three-supplier solicitation collection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from itaa_application.dispatch_service import DispatchService
from itaa_application.errors import ApplicationError
from itaa_application.offer_boundary import AuthorizedResponseBinding, CollectedSupplierResponse
from itaa_application.supplier_port import (
    SUPPLIER_DECLINE_REASONS,
    Clock,
    ClosedReason,
    SupplierAttempt,
    SupplierPort,
    SupplierTerminal,
    TerminalKind,
)
from itaa_domain.identifiers import (
    ActorId,
    ApprovalId,
    CorrelationId,
    OfferId,
    SignatureHandle,
    SupplierToken,
)
from itaa_domain.value_objects import ActorRef, require_utc
from itaa_policy.envelopes import SolicitationBinding, SupplierEnvelope
from itaa_policy.isolation import SupplierInvitationToken

_UNMAPPED = frozenset(
    {TerminalKind.TIMED_OUT, TerminalKind.DENIED, TerminalKind.FAILED, TerminalKind.LATE}
)


@dataclass(frozen=True, slots=True)
class SolicitationSlot:
    supplier_token: SupplierToken
    offer_id: OfferId
    signature: SignatureHandle
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class CollectionResult:
    responses: tuple[CollectedSupplierResponse, ...]
    invoked: tuple[SupplierToken, ...]
    missing: tuple[CorrelationId, ...]

    @property
    def terminals(self) -> tuple[CollectedSupplierResponse, ...]:
        return self.responses


class IsolatedMailbox:
    """Buyer-side private response slots. Suppliers never receive this object."""

    def __init__(self, invitations: tuple[SupplierInvitationToken, ...]) -> None:
        self._allowed = {item.to_primitive() for item in invitations}
        self._results: dict[str, SupplierTerminal] = {}

    def submit(self, invitation: SupplierInvitationToken, result: SupplierTerminal) -> None:
        key = invitation.to_primitive()
        if key not in self._allowed:
            raise ApplicationError("invitation", "wrong_channel")
        if result.invitation != invitation:
            raise ApplicationError("invitation", "wrong_channel")
        if key in self._results:
            raise ApplicationError("response", "duplicate")
        self._results[key] = result

    def get(self, invitation: SupplierInvitationToken) -> SupplierTerminal | None:
        return self._results.get(invitation.to_primitive())


class _PrivateSlot:
    def __init__(self, invitation: SupplierInvitationToken) -> None:
        self.invitation = invitation
        self.result: CollectedSupplierResponse | None = None


class SolicitationCollector:
    """Collect exactly three isolated supplier terminals through WP-04 dispatch."""

    def __init__(self, dispatch: DispatchService) -> None:
        self._dispatch = dispatch

    def collect(
        self,
        *,
        approval_id: ApprovalId,
        binding: SolicitationBinding,
        slots: tuple[SolicitationSlot, ...],
        ports: dict[SupplierToken, SupplierPort],
        deadline: datetime,
        actor: ActorRef,
        owner_id: ActorId,
        clock: Clock,
    ) -> CollectionResult:
        close_at = require_utc(deadline, "deadline")
        if len(slots) != 3:
            raise ApplicationError("assignments", "must_be_three")
        tokens = [item.supplier_token for item in slots]
        if len(set(tokens)) != 3:
            raise ApplicationError("assignments", "must_be_unique")
        if len(set(item.correlation_id for item in slots)) != 3:
            raise ApplicationError("assignments", "must_be_unique")
        envelopes = {item.assignment.supplier_token: item for item in binding.envelopes}
        mailboxes = {
            item.supplier_token: _PrivateSlot(envelopes[item.supplier_token].assignment.invitation)
            for item in slots
            if item.supplier_token in envelopes
        }
        if len(mailboxes) != 3:
            raise ApplicationError("assignments", "unknown_supplier")
        for slot in slots:
            if slot.supplier_token not in ports:
                raise ApplicationError("port", "missing")
        invoked: list[SupplierToken] = []
        order = tuple(sorted(tokens, key=lambda item: item.to_primitive()))
        stop_remaining = False
        for token in order:
            if stop_remaining:
                break
            instant = clock.now()
            if instant >= close_at:
                _timeout_remaining(slots, mailboxes, envelopes, instant)
                break
            slot = next(item for item in slots if item.supplier_token == token)
            authorized = self._dispatch.authorize(
                approval_id,
                binding=binding,
                supplier_token=token,
                occurred_at=instant,
                actor=actor,
                owner_id=owner_id,
            )
            if not authorized.allowed or authorized.envelope is None:
                _write(
                    mailboxes[token],
                    _closed(
                        envelopes[token],
                        slot,
                        TerminalKind.DENIED,
                        ClosedReason.DISPATCH_DENIED,
                        instant,
                    ),
                )
                continue
            sealed = AuthorizedResponseBinding.from_authorization(
                authorized, correlation_id=slot.correlation_id
            )
            invitation = authorized.envelope.assignment.invitation
            invoked.append(token)
            try:
                result = ports[token].attempt(
                    SupplierAttempt(
                        envelope=authorized.envelope,
                        occurred_at=instant,
                        deadline=close_at,
                        invitation=invitation,
                        offer_id=slot.offer_id,
                        signature=slot.signature,
                        correlation_id=slot.correlation_id,
                    )
                )
            except Exception:
                received_at = clock.now()
                collected = _late_or_failed(sealed, received_at, close_at)
                _write(mailboxes[token], collected)
                if collected.kind is TerminalKind.LATE:
                    _timeout_remaining(slots, mailboxes, envelopes, received_at)
                    stop_remaining = True
                continue
            received_at = clock.now()
            try:
                collected = _normalize(
                    sealed, result, token, slot, invitation, received_at, close_at
                )
            except Exception:
                collected = _invalid_or_late(sealed, received_at, close_at)
            _write(mailboxes[token], collected)
            if collected.kind is TerminalKind.LATE and received_at >= close_at:
                _timeout_remaining(slots, mailboxes, envelopes, received_at)
                stop_remaining = True
        terminals = tuple(
            _require_terminal(mailboxes[item.supplier_token], item, envelopes, clock.now())
            for item in sorted(slots, key=lambda row: row.supplier_token.to_primitive())
        )
        missing = tuple(item.correlation_id for item in terminals if item.kind in _UNMAPPED)
        return CollectionResult(responses=terminals, invoked=tuple(invoked), missing=missing)


def _write(box: _PrivateSlot, result: CollectedSupplierResponse) -> None:
    if box.result is not None:
        raise ApplicationError("response", "duplicate")
    box.result = result


def _closed(
    envelope: SupplierEnvelope,
    slot: SolicitationSlot,
    kind: TerminalKind,
    reason: ClosedReason,
    received_at: datetime,
) -> CollectedSupplierResponse:
    return CollectedSupplierResponse.seal(
        supplier_token=slot.supplier_token,
        invitation=envelope.assignment.invitation,
        correlation_id=slot.correlation_id,
        kind=kind,
        received_at=received_at,
        reason=reason,
    )


def _invalid_or_late(
    binding: AuthorizedResponseBinding, received_at: datetime, deadline: datetime
) -> CollectedSupplierResponse:
    if received_at >= deadline:
        return _seal_from_binding(
            binding,
            kind=TerminalKind.LATE,
            received_at=received_at,
            reason=ClosedReason.LATE,
        )
    return _malformed(binding, received_at)


def _late_or_failed(
    binding: AuthorizedResponseBinding, received_at: datetime, deadline: datetime
) -> CollectedSupplierResponse:
    if received_at >= deadline:
        return CollectedSupplierResponse.seal(
            supplier_token=binding.supplier_token,
            invitation=binding.invitation,
            correlation_id=binding.correlation_id,
            kind=TerminalKind.LATE,
            received_at=received_at,
            reason=ClosedReason.LATE,
            binding=binding,
        )
    return CollectedSupplierResponse.seal(
        supplier_token=binding.supplier_token,
        invitation=binding.invitation,
        correlation_id=binding.correlation_id,
        kind=TerminalKind.FAILED,
        received_at=received_at,
        reason=ClosedReason.FAILED,
        binding=binding,
    )


def _seal_from_binding(
    binding: AuthorizedResponseBinding,
    *,
    kind: TerminalKind,
    received_at: datetime,
    reason: ClosedReason | None = None,
    payload: object = None,
    completed_at: datetime | None = None,
) -> CollectedSupplierResponse:
    return CollectedSupplierResponse.seal(
        supplier_token=binding.supplier_token,
        invitation=binding.invitation,
        correlation_id=binding.correlation_id,
        kind=kind,
        received_at=received_at,
        reason=reason,
        payload=payload,
        completed_at=completed_at,
        binding=binding,
    )


def _normalize(
    binding: AuthorizedResponseBinding,
    result: object,
    expected: SupplierToken,
    slot: SolicitationSlot,
    invitation: SupplierInvitationToken,
    received_at: datetime,
    deadline: datetime,
) -> CollectedSupplierResponse:
    if received_at >= deadline:
        return _seal_from_binding(
            binding,
            kind=TerminalKind.LATE,
            received_at=received_at,
            reason=ClosedReason.LATE,
        )
    if type(result) is not SupplierTerminal:
        return _malformed(binding, received_at)
    if (
        type(result.kind) is not TerminalKind
        or type(result.supplier_token) is not SupplierToken
        or type(result.correlation_id) is not CorrelationId
        or type(result.invitation) is not SupplierInvitationToken
        or (result.reason is not None and type(result.reason) is not ClosedReason)
    ):
        return _malformed(binding, received_at)
    if (
        result.supplier_token != expected
        or result.correlation_id != slot.correlation_id
        or result.invitation != invitation
        or invitation != binding.invitation
    ):
        return _seal_from_binding(
            binding,
            kind=TerminalKind.INVALID,
            received_at=received_at,
            reason=ClosedReason.WRONG_CHANNEL,
        )
    if result.completed_at > received_at or result.completed_at >= deadline:
        return _malformed(binding, received_at)
    if result.kind is TerminalKind.OFFER:
        if result.reason is not None or result.payload is None:
            return _malformed(binding, received_at)
        return _seal_from_binding(
            binding,
            kind=TerminalKind.OFFER,
            received_at=received_at,
            payload=result.payload,
            completed_at=result.completed_at,
        )
    if (
        result.kind is TerminalKind.DECLINED
        and result.reason in SUPPLIER_DECLINE_REASONS
        and result.payload is None
    ):
        return _seal_from_binding(
            binding,
            kind=TerminalKind.DECLINED,
            received_at=received_at,
            reason=result.reason,
            completed_at=result.completed_at,
        )
    return _malformed(binding, received_at)


def _malformed(
    binding: AuthorizedResponseBinding, received_at: datetime
) -> CollectedSupplierResponse:
    return _seal_from_binding(
        binding,
        kind=TerminalKind.INVALID,
        received_at=received_at,
        reason=ClosedReason.MALFORMED,
    )


def _timeout_remaining(
    slots: tuple[SolicitationSlot, ...],
    mailboxes: dict[SupplierToken, _PrivateSlot],
    envelopes: dict[SupplierToken, SupplierEnvelope],
    instant: datetime,
) -> None:
    for slot in slots:
        box = mailboxes[slot.supplier_token]
        if box.result is not None:
            continue
        box.result = _closed(
            envelopes[slot.supplier_token],
            slot,
            TerminalKind.TIMED_OUT,
            ClosedReason.TIMEOUT,
            instant,
        )


def _require_terminal(
    box: _PrivateSlot,
    slot: SolicitationSlot,
    envelopes: dict[SupplierToken, SupplierEnvelope],
    instant: datetime,
) -> CollectedSupplierResponse:
    if box.result is not None:
        return box.result
    box.result = _closed(
        envelopes[slot.supplier_token],
        slot,
        TerminalKind.TIMED_OUT,
        ClosedReason.TIMEOUT,
        instant,
    )
    return box.result
