from __future__ import annotations

import pytest
from test_wp05_solicitation import AdvanceAfterPort, SpyPort, _collect, _collector, fake_ports
from wp04_helpers import (
    A2_ID,
    CORRELATION,
    EXPIRES_AT,
    INVITATIONS,
    OCCURRED_AT,
    REVOKE_ID,
    SUPPLIERS,
)
from wp05_helpers import CORRELATIONS

from itaa_application.approval_service import ApprovalService
from itaa_application.errors import ApplicationError
from itaa_application.supplier_port import (
    BUYER_OWNED_KINDS,
    BUYER_OWNED_REASONS,
    SUPPLIER_DECLINE_REASONS,
    SUPPLIER_ORIGINATED_KINDS,
    ClosedReason,
    FrozenClock,
    SupplierAttempt,
    SupplierTerminal,
    TerminalKind,
)
from itaa_policy.approvals import ApprovalRevocation


def _fabricate(
    request: SupplierAttempt,
    kind: TerminalKind,
    reason: ClosedReason | None,
    payload: object = None,
) -> SupplierTerminal:
    terminal = object.__new__(SupplierTerminal)
    object.__setattr__(terminal, "kind", kind)
    object.__setattr__(terminal, "supplier_token", request.envelope.assignment.supplier_token)
    object.__setattr__(terminal, "correlation_id", request.correlation_id)
    object.__setattr__(terminal, "invitation", request.invitation)
    object.__setattr__(terminal, "completed_at", request.occurred_at)
    object.__setattr__(terminal, "reason", reason)
    object.__setattr__(terminal, "payload", payload)
    return terminal


def test_closed_vocabularies_partition_kinds_and_reasons() -> None:
    assert frozenset(TerminalKind) == SUPPLIER_ORIGINATED_KINDS | BUYER_OWNED_KINDS
    assert frozenset() == SUPPLIER_ORIGINATED_KINDS & BUYER_OWNED_KINDS
    assert frozenset(ClosedReason) == SUPPLIER_DECLINE_REASONS | BUYER_OWNED_REASONS
    assert frozenset() == SUPPLIER_DECLINE_REASONS & BUYER_OWNED_REASONS


@pytest.mark.parametrize("kind", sorted(BUYER_OWNED_KINDS, key=lambda item: item.value))
def test_supplier_terminal_rejects_buyer_owned_kinds(kind: TerminalKind) -> None:
    with pytest.raises(ApplicationError, match="kind: invalid_enum") as captured:
        SupplierTerminal(
            kind,
            SUPPLIERS[0],
            CORRELATIONS[0],
            INVITATIONS[0],
            OCCURRED_AT,
            ClosedReason.INSUFFICIENT_CAPACITY,
        )
    text = str(captured.value)
    assert kind.value not in text
    assert "alice@" not in text


@pytest.mark.parametrize("reason", sorted(BUYER_OWNED_REASONS, key=lambda item: item.value))
def test_supplier_terminal_rejects_buyer_owned_decline_reasons(reason: ClosedReason) -> None:
    with pytest.raises(ApplicationError, match="reason: invalid_enum") as captured:
        SupplierTerminal(
            TerminalKind.DECLINED,
            SUPPLIERS[0],
            CORRELATIONS[0],
            INVITATIONS[0],
            OCCURRED_AT,
            reason,
        )
    text = str(captured.value)
    assert reason.value not in text
    assert "alice@" not in text


@pytest.mark.parametrize("kind", sorted(BUYER_OWNED_KINDS, key=lambda item: item.value))
def test_fabricated_buyer_owned_kind_is_invalid_malformed(kind: TerminalKind) -> None:
    collector, binding, _repo = _collector()

    class Bypass:
        def attempt(self, request: SupplierAttempt) -> SupplierTerminal:
            return _fabricate(
                request,
                kind,
                ClosedReason.LATE,
                payload={"simulation": True, "email": "alice@example.com"},
            )

    spies = {token: SpyPort(port) for token, port in fake_ports().items()}
    spies[SUPPLIERS[0]] = SpyPort(Bypass())  # type: ignore[arg-type]
    result = _collect(collector, binding, spies)
    kinds = {item.supplier_token: item.kind for item in result.terminals}
    reasons = {item.supplier_token: item.reason for item in result.terminals}
    assert kinds[SUPPLIERS[0]] is TerminalKind.INVALID
    assert reasons[SUPPLIERS[0]] is ClosedReason.MALFORMED
    assert kinds[SUPPLIERS[1]] is TerminalKind.OFFER
    assert kinds[SUPPLIERS[2]] is TerminalKind.OFFER
    assert spies[SUPPLIERS[1]].calls == 1
    assert spies[SUPPLIERS[2]].calls == 1
    targeted = next(item for item in result.terminals if item.supplier_token == SUPPLIERS[0])
    assert targeted.payload is None
    assert targeted.correlation_id not in result.missing
    assert targeted.kind is not TerminalKind.LATE
    assert targeted.kind is not TerminalKind.DENIED
    assert targeted.kind is not TerminalKind.TIMED_OUT
    assert targeted.kind is not TerminalKind.FAILED
    haystack = str(result)
    assert "alice@" not in haystack
    assert "example.com" not in haystack


def test_legitimate_supplier_decline_remains_declined() -> None:
    collector, binding, _repo = _collector()

    class BusinessDecline:
        def attempt(self, request: SupplierAttempt) -> SupplierTerminal:
            return SupplierTerminal(
                TerminalKind.DECLINED,
                request.envelope.assignment.supplier_token,
                request.correlation_id,
                request.invitation,
                request.occurred_at,
                ClosedReason.INSUFFICIENT_CAPACITY,
            )

    spies = {token: SpyPort(port) for token, port in fake_ports().items()}
    spies[SUPPLIERS[0]] = SpyPort(BusinessDecline())
    result = _collect(collector, binding, spies)
    kinds = {item.supplier_token: item.kind for item in result.terminals}
    reasons = {item.supplier_token: item.reason for item in result.terminals}
    assert kinds[SUPPLIERS[0]] is TerminalKind.DECLINED
    assert reasons[SUPPLIERS[0]] is ClosedReason.INSUFFICIENT_CAPACITY
    assert kinds[SUPPLIERS[1]] is TerminalKind.OFFER
    assert kinds[SUPPLIERS[2]] is TerminalKind.OFFER
    declined = next(item for item in result.terminals if item.supplier_token == SUPPLIERS[0])
    assert declined.payload is None


def test_buyer_timeout_and_port_failure_remain_buyer_owned() -> None:
    collector, binding, _repo = _collector()
    spies = {token: SpyPort(port) for token, port in fake_ports().items()}
    timed = _collect(collector, binding, spies, FrozenClock(EXPIRES_AT))
    assert all(item.kind is TerminalKind.TIMED_OUT for item in timed.terminals)
    assert all(item.reason is ClosedReason.TIMEOUT for item in timed.terminals)
    assert all(item.payload is None for item in timed.terminals)
    assert all(spy.calls == 0 for spy in spies.values())

    class Boom:
        def attempt(self, request: SupplierAttempt) -> SupplierTerminal:
            raise RuntimeError("alice@example.com")

    ports = fake_ports()
    ports[SUPPLIERS[0]] = Boom()  # type: ignore[assignment]
    failed = _collect(collector, binding, ports)
    kinds = {item.supplier_token: item.kind for item in failed.terminals}
    assert kinds[SUPPLIERS[0]] is TerminalKind.FAILED
    assert kinds[SUPPLIERS[1]] is TerminalKind.OFFER
    assert kinds[SUPPLIERS[2]] is TerminalKind.OFFER
    targeted = next(item for item in failed.terminals if item.supplier_token == SUPPLIERS[0])
    assert targeted.reason is ClosedReason.FAILED
    assert targeted.payload is None
    assert "alice@" not in str(failed)


def test_a2_denial_and_buyer_clock_late_remain_buyer_owned() -> None:
    collector, binding, repo = _collector()
    ApprovalService(repo).revoke(
        ApprovalRevocation(
            revocation_id=REVOKE_ID,
            target_id=A2_ID,
            occurred_at=OCCURRED_AT,
            correlation_id=CORRELATION,
        )
    )
    spies = {token: SpyPort(port) for token, port in fake_ports().items()}
    denied = _collect(collector, binding, spies)
    assert all(item.kind is TerminalKind.DENIED for item in denied.terminals)
    assert all(item.reason is ClosedReason.DISPATCH_DENIED for item in denied.terminals)
    assert all(item.payload is None for item in denied.terminals)
    assert all(spy.calls == 0 for spy in spies.values())

    collector, binding, _repo = _collector()
    clock = FrozenClock(OCCURRED_AT)
    inner = fake_ports()
    first = tuple(sorted(SUPPLIERS, key=lambda item: item.to_primitive()))[0]
    ports = {
        token: AdvanceAfterPort(port, clock, first) if token == first else port
        for token, port in inner.items()
    }
    late = _collect(collector, binding, ports, clock)
    kinds = {item.supplier_token: item.kind for item in late.terminals}
    assert kinds[first] is TerminalKind.LATE
    assert all(item.payload is None for item in late.terminals if item.kind is TerminalKind.LATE)
    assert ClosedReason.LATE in {
        item.reason for item in late.terminals if item.kind is TerminalKind.LATE
    }


def test_fabricated_declined_buyer_reason_is_invalid_malformed() -> None:
    collector, binding, _repo = _collector()

    class Bypass:
        def attempt(self, request: SupplierAttempt) -> SupplierTerminal:
            return _fabricate(request, TerminalKind.DECLINED, ClosedReason.TIMEOUT)

    spies = {token: SpyPort(port) for token, port in fake_ports().items()}
    spies[SUPPLIERS[0]] = SpyPort(Bypass())  # type: ignore[arg-type]
    result = _collect(collector, binding, spies)
    kinds = {item.supplier_token: item.kind for item in result.terminals}
    reasons = {item.supplier_token: item.reason for item in result.terminals}
    assert kinds[SUPPLIERS[0]] is TerminalKind.INVALID
    assert reasons[SUPPLIERS[0]] is ClosedReason.MALFORMED
    assert kinds[SUPPLIERS[1]] is TerminalKind.OFFER
    assert kinds[SUPPLIERS[2]] is TerminalKind.OFFER
    targeted = next(item for item in result.terminals if item.supplier_token == SUPPLIERS[0])
    assert targeted.payload is None
    assert targeted.correlation_id not in result.missing
