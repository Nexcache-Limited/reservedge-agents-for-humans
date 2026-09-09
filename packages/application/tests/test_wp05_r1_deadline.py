from __future__ import annotations

from datetime import timedelta

from test_wp05_solicitation import (
    ConstantPort,
    SpyPort,
    TimedPort,
    _collect,
    _collector,
    fake_ports,
)
from wp04_helpers import EXPIRES_AT, OCCURRED_AT, SUPPLIERS

from itaa_application.supplier_port import ClosedReason, FrozenClock, TerminalKind


class ClockAdvancingPort:
    def __init__(self, inner, clock: FrozenClock, instant) -> None:
        self.inner = inner
        self.clock = clock
        self.instant = instant

    def attempt(self, request):
        result = self.inner.attempt(request)
        self.clock.set(self.instant)
        return result


def test_buyer_receipt_at_deadline_is_late_even_if_supplier_claims_early() -> None:
    collector, binding, _repo = _collector()
    clock = FrozenClock(OCCURRED_AT)
    ports = {
        token: ClockAdvancingPort(port, clock, EXPIRES_AT) if token == SUPPLIERS[0] else port
        for token, port in fake_ports().items()
    }
    result = _collect(collector, binding, ports, clock)
    kinds = {item.supplier_token: item.kind for item in result.terminals}
    assert kinds[SUPPLIERS[0]] is TerminalKind.LATE
    assert result.terminals[0].payload is None or kinds[SUPPLIERS[0]] is TerminalKind.LATE
    assert all(item.payload is None for item in result.terminals if item.kind is TerminalKind.LATE)


def test_supplier_claim_after_deadline_with_early_receipt_is_invalid() -> None:
    collector, binding, _repo = _collector()
    ports = {
        SUPPLIERS[0]: TimedPort(OCCURRED_AT),
        SUPPLIERS[1]: TimedPort(EXPIRES_AT),
        SUPPLIERS[2]: TimedPort(EXPIRES_AT + timedelta(microseconds=1)),
    }
    result = _collect(collector, binding, ports, FrozenClock(OCCURRED_AT))
    kinds = {item.supplier_token: item.kind for item in result.terminals}
    assert kinds[SUPPLIERS[0]] is TerminalKind.OFFER
    assert kinds[SUPPLIERS[1]] is TerminalKind.INVALID
    assert kinds[SUPPLIERS[2]] is TerminalKind.INVALID


def test_declined_invalid_failed_at_deadline_become_late() -> None:
    collector, binding, _repo = _collector()
    clock = FrozenClock(OCCURRED_AT)

    class LateDecline:
        def attempt(self, request):
            result = ConstantPort(
                TerminalKind.DECLINED, ClosedReason.INSUFFICIENT_CAPACITY
            ).attempt(request)
            clock.set(EXPIRES_AT)
            return result

    class LateInvalid:
        def attempt(self, request):
            from itaa_application.supplier_port import SupplierTerminal

            result = object.__new__(SupplierTerminal)
            object.__setattr__(result, "kind", TerminalKind.INVALID)
            object.__setattr__(result, "supplier_token", request.envelope.assignment.supplier_token)
            object.__setattr__(result, "correlation_id", request.correlation_id)
            object.__setattr__(result, "invitation", request.invitation)
            object.__setattr__(result, "completed_at", request.occurred_at)
            object.__setattr__(result, "reason", ClosedReason.MALFORMED)
            object.__setattr__(result, "payload", {"simulation": True})
            clock.set(EXPIRES_AT)
            return result

    order = tuple(sorted(SUPPLIERS, key=lambda item: item.to_primitive()))
    ports = {
        order[0]: LateDecline(),
        order[1]: LateInvalid(),
        order[2]: fake_ports()[order[2]],
    }
    result = _collect(collector, binding, ports, clock)
    kinds = {item.supplier_token: item.kind for item in result.terminals}
    assert kinds[order[0]] is TerminalKind.LATE
    assert kinds[order[1]] is TerminalKind.TIMED_OUT
    assert kinds[order[2]] is TerminalKind.TIMED_OUT


def test_clock_advancement_during_first_call_lates_that_supplier() -> None:
    collector, binding, _repo = _collector()
    clock = FrozenClock(OCCURRED_AT)
    order = tuple(sorted(SUPPLIERS, key=lambda item: item.to_primitive()))
    spies = {token: SpyPort(port) for token, port in fake_ports().items()}

    class AdvanceFirst:
        def __init__(self, inner, clock: FrozenClock, first) -> None:
            self.inner = inner
            self.clock = clock
            self.first = first

        def attempt(self, request):
            result = self.inner.attempt(request)
            if request.envelope.assignment.supplier_token == self.first:
                self.clock.set(EXPIRES_AT)
            return result

    ports = {
        token: AdvanceFirst(spy, clock, order[0]) if token == order[0] else spy
        for token, spy in spies.items()
    }
    result = _collect(collector, binding, ports, clock)
    kinds = {item.supplier_token: item.kind for item in result.terminals}
    assert kinds[order[0]] is TerminalKind.LATE
    assert kinds[order[1]] is TerminalKind.TIMED_OUT
    assert kinds[order[2]] is TerminalKind.TIMED_OUT
    assert spies[order[1]].calls == 0
    assert spies[order[2]].calls == 0
