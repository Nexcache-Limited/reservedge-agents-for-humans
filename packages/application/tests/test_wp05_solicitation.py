from __future__ import annotations

from inspect import signature
from itertools import permutations

import pytest
from fakes import InMemoryApprovalRepository
from test_rework_wp04_r1 import _a2_for, _binding
from wp04_helpers import (
    A2_ID,
    BUYER,
    CORRELATION,
    EXPIRES_AT,
    INVITATIONS,
    OCCURRED_AT,
    OWNER,
    REVOKE_ID,
    SUPPLIERS,
)

from itaa_application.approval_service import ApprovalService
from itaa_application.dispatch_service import DispatchService
from itaa_application.errors import ApplicationError
from itaa_application.solicitation_service import (
    IsolatedMailbox,
    SolicitationCollector,
    SolicitationSlot,
)
from itaa_application.supplier_port import (
    ClosedReason,
    FrozenClock,
    SupplierAttempt,
    SupplierPort,
    SupplierTerminal,
    TerminalKind,
)
from itaa_domain.identifiers import CorrelationId, OfferId, SignatureHandle, SupplierToken
from itaa_policy.approvals import ApprovalRevocation

SLOTS = (
    SolicitationSlot(
        SUPPLIERS[0],
        OfferId("of_01k2m3n4p5q6r7s8t9v0w1x2a4"),
        SignatureHandle("sg_01k2m3n4p5q6r7s8t9v0w1x2h4"),
        CorrelationId("cr_01k2m3n4p5q6r7s8t9v0w1x2m1"),
    ),
    SolicitationSlot(
        SUPPLIERS[1],
        OfferId("of_01k2m3n4p5q6r7s8t9v0w1x2a5"),
        SignatureHandle("sg_01k2m3n4p5q6r7s8t9v0w1x2h5"),
        CorrelationId("cr_01k2m3n4p5q6r7s8t9v0w1x2m2"),
    ),
    SolicitationSlot(
        SUPPLIERS[2],
        OfferId("of_01k2m3n4p5q6r7s8t9v0w1x2a6"),
        SignatureHandle("sg_01k2m3n4p5q6r7s8t9v0w1x2h6"),
        CorrelationId("cr_01k2m3n4p5q6r7s8t9v0w1x2m3"),
    ),
)


def _payload(token: SupplierToken) -> dict[str, object]:
    return {"simulation": True, "supplierToken": token.to_primitive()}


class FakeOfferPort:
    def attempt(self, request: SupplierAttempt) -> SupplierTerminal:
        token = request.envelope.assignment.supplier_token
        return SupplierTerminal(
            TerminalKind.OFFER,
            token,
            request.correlation_id,
            request.invitation,
            request.occurred_at,
            payload=_payload(token),
        )


def fake_ports() -> dict[SupplierToken, FakeOfferPort]:
    return {token: FakeOfferPort() for token in SUPPLIERS}


class SpyPort:
    def __init__(self, inner: SupplierPort) -> None:
        self.inner = inner
        self.calls = 0
        self.envelopes: list[object] = []

    def attempt(self, request: SupplierAttempt) -> SupplierTerminal:
        self.calls += 1
        self.envelopes.append(request.envelope)
        return self.inner.attempt(request)


class RecordingBagPort:
    def __init__(self, bag: list[object], inner: SupplierPort) -> None:
        self.bag = bag
        self.inner = inner

    def attempt(self, request: SupplierAttempt) -> SupplierTerminal:
        leaked = getattr(request, "shared_results", None)
        if leaked is not None:
            self.bag.append(leaked)
        return self.inner.attempt(request)


class ConstantPort:
    def __init__(self, kind: TerminalKind, reason: ClosedReason) -> None:
        self.kind = kind
        self.reason = reason

    def attempt(self, request: SupplierAttempt) -> SupplierTerminal:
        return SupplierTerminal(
            self.kind,
            request.envelope.assignment.supplier_token,
            request.correlation_id,
            request.invitation,
            request.occurred_at,
            self.reason,
        )


class TimedPort:
    def __init__(self, completed_at) -> None:
        self.completed_at = completed_at

    def attempt(self, request: SupplierAttempt) -> SupplierTerminal:
        token = request.envelope.assignment.supplier_token
        return SupplierTerminal(
            TerminalKind.OFFER,
            token,
            request.correlation_id,
            request.invitation,
            self.completed_at,
            payload=_payload(token),
        )


class AdvanceAfterPort:
    def __init__(self, inner: SupplierPort, clock: FrozenClock, token: SupplierToken) -> None:
        self.inner = inner
        self.clock = clock
        self.token = token

    def attempt(self, request: SupplierAttempt) -> SupplierTerminal:
        result = self.inner.attempt(request)
        if request.envelope.assignment.supplier_token == self.token:
            self.clock.set(EXPIRES_AT)
        return result


def _collector():
    repo = InMemoryApprovalRepository()
    approvals = ApprovalService(repo)
    binding = _binding()
    approvals.issue(_a2_for(binding))
    return SolicitationCollector(DispatchService(repo)), binding, repo


def _collect(collector, binding, ports, clock: FrozenClock | None = None):
    return collector.collect(
        approval_id=A2_ID,
        binding=binding,
        slots=SLOTS,
        ports=ports,
        deadline=EXPIRES_AT,
        actor=BUYER,
        owner_id=OWNER,
        clock=clock or FrozenClock(OCCURRED_AT),
    )


def test_three_seeded_suppliers_produce_isolated_offers() -> None:
    collector, binding, _repo = _collector()
    spies = {token: SpyPort(port) for token, port in fake_ports().items()}
    result = _collect(collector, binding, spies)
    assert [item.kind for item in result.terminals] == [TerminalKind.OFFER] * 3
    assert set(result.invoked) == set(SUPPLIERS)
    for spy in spies.values():
        assert spy.calls == 1
        payload = spy.envelopes[0].payload_dict()
        assert "email" not in str(payload)
        assert payload.get("schemaVersion") == "1.0"


def test_all_port_insertion_orders_are_stable() -> None:
    collector, binding, _repo = _collector()
    first = None
    for order in permutations(SUPPLIERS):
        ports = {token: FakeOfferPort() for token in order}
        result = _collect(collector, binding, ports)
        kinds = [item.kind.value for item in result.terminals]
        ids = [item.supplier_token.to_primitive() for item in result.terminals]
        snapshot = (tuple(kinds), tuple(ids))
        if first is None:
            first = snapshot
        assert snapshot == first


def test_timeout_preserves_other_offers_and_does_not_fabricate() -> None:
    collector, binding, _repo = _collector()
    clock = FrozenClock(OCCURRED_AT)
    inner = fake_ports()
    second = tuple(sorted(SUPPLIERS, key=lambda item: item.to_primitive()))[1]
    spies = {token: SpyPort(AdvanceAfterPort(port, clock, second)) for token, port in inner.items()}
    result = _collect(collector, binding, spies, clock)
    kinds = {item.supplier_token: item.kind for item in result.terminals}
    assert kinds[second] is TerminalKind.LATE
    timed_out = [token for token, kind in kinds.items() if kind is TerminalKind.TIMED_OUT]
    offered = [token for token, kind in kinds.items() if kind is TerminalKind.OFFER]
    assert timed_out
    assert offered
    assert spies[timed_out[0]].calls == 0
    assert SLOTS[list(SUPPLIERS).index(timed_out[0])].correlation_id in result.missing


def test_denied_dispatch_never_invokes_simulator() -> None:
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
    result = _collect(collector, binding, spies)
    assert all(item.kind is TerminalKind.DENIED for item in result.terminals)
    assert result.invoked == ()
    assert all(spy.calls == 0 for spy in spies.values())


def test_exactly_three_unique_assignments_required() -> None:
    collector, binding, _repo = _collector()
    with pytest.raises(ApplicationError, match="must_be_three"):
        collector.collect(
            approval_id=A2_ID,
            binding=binding,
            slots=SLOTS[:2],
            ports=fake_ports(),
            deadline=EXPIRES_AT,
            actor=BUYER,
            owner_id=OWNER,
            clock=FrozenClock(OCCURRED_AT),
        )


def test_mailbox_rejects_wrong_channel_and_duplicate() -> None:
    box = IsolatedMailbox((INVITATIONS[0], INVITATIONS[1]))
    result = SupplierTerminal(
        TerminalKind.DECLINED,
        SUPPLIERS[0],
        SLOTS[0].correlation_id,
        INVITATIONS[0],
        OCCURRED_AT,
        ClosedReason.INSUFFICIENT_CAPACITY,
    )
    box.submit(INVITATIONS[0], result)
    with pytest.raises(ApplicationError, match="duplicate"):
        box.submit(INVITATIONS[0], result)
    with pytest.raises(ApplicationError, match="wrong_channel"):
        box.submit(INVITATIONS[2], result)


def test_adversarial_supplier_cannot_see_shared_collection() -> None:
    bag: list[object] = []
    collector, binding, _repo = _collector()
    ports = {token: RecordingBagPort(bag, port) for token, port in fake_ports().items()}
    _collect(collector, binding, ports)
    assert bag == []


def test_one_decline_preserves_other_offers() -> None:
    collector, binding, _repo = _collector()
    ports = fake_ports()
    ports[SUPPLIERS[0]] = ConstantPort(TerminalKind.DECLINED, ClosedReason.INSUFFICIENT_CAPACITY)
    result = _collect(collector, binding, ports)
    kinds = {item.supplier_token: item.kind for item in result.terminals}
    assert kinds[SUPPLIERS[0]] is TerminalKind.DECLINED
    assert kinds[SUPPLIERS[1]] is TerminalKind.OFFER
    assert kinds[SUPPLIERS[2]] is TerminalKind.OFFER


def test_deadline_already_passed_times_out_without_invoke() -> None:
    collector, binding, _repo = _collector()
    spies = {token: SpyPort(port) for token, port in fake_ports().items()}
    result = _collect(collector, binding, spies, FrozenClock(EXPIRES_AT))
    assert all(item.kind is TerminalKind.TIMED_OUT for item in result.terminals)
    assert result.invoked == ()
    assert all(spy.calls == 0 for spy in spies.values())


def test_production_collector_has_no_timeout_knobs() -> None:
    names = signature(SolicitationCollector.collect).parameters
    assert "timeout_tokens" not in names
    assert "completion_order" not in names
    assert "clock" in names


def test_duplicate_correlations_fail_before_collection() -> None:
    collector, binding, _repo = _collector()
    duplicated = (
        SLOTS[0],
        SLOTS[1],
        SolicitationSlot(
            SLOTS[2].supplier_token, SLOTS[2].offer_id, SLOTS[2].signature, SLOTS[0].correlation_id
        ),
    )
    with pytest.raises(ApplicationError, match="must_be_unique"):
        collector.collect(
            approval_id=A2_ID,
            binding=binding,
            slots=duplicated,
            ports=fake_ports(),
            deadline=EXPIRES_AT,
            actor=BUYER,
            owner_id=OWNER,
            clock=FrozenClock(OCCURRED_AT),
        )
    collector, binding, _repo = _collector()
    ports = fake_ports()
    del ports[SUPPLIERS[2]]
    with pytest.raises(ApplicationError, match="port: missing"):
        _collect(collector, binding, ports)
    duplicated = (
        SLOTS[0],
        SLOTS[1],
        SolicitationSlot(
            SLOTS[0].supplier_token, SLOTS[2].offer_id, SLOTS[2].signature, SLOTS[2].correlation_id
        ),
    )
    with pytest.raises(ApplicationError, match="must_be_unique"):
        collector.collect(
            approval_id=A2_ID,
            binding=binding,
            slots=duplicated,
            ports=fake_ports(),
            deadline=EXPIRES_AT,
            actor=BUYER,
            owner_id=OWNER,
            clock=FrozenClock(OCCURRED_AT),
        )


def test_malformed_and_late_exception_do_not_abort_collection() -> None:
    collector, binding, _repo = _collector()

    class Malformed:
        def attempt(self, request):
            return "not-a-terminal"

    clock = FrozenClock(OCCURRED_AT)

    class BoomLate:
        def attempt(self, request):
            clock.set(EXPIRES_AT)
            raise RuntimeError("alice@example.com")

    ports = fake_ports()
    ports[SUPPLIERS[0]] = Malformed()
    result = _collect(collector, binding, ports)
    kinds = {item.supplier_token: item.kind for item in result.terminals}
    assert kinds[SUPPLIERS[0]] is TerminalKind.INVALID
    assert kinds[SUPPLIERS[1]] is TerminalKind.OFFER
    assert kinds[SUPPLIERS[2]] is TerminalKind.OFFER
    ports = fake_ports()
    order = tuple(sorted(SUPPLIERS, key=lambda item: item.to_primitive()))
    ports[order[0]] = BoomLate()
    result = _collect(collector, binding, ports, clock)
    kinds = {item.supplier_token: item.kind for item in result.terminals}
    assert kinds[order[0]] is TerminalKind.LATE
    assert kinds[order[1]] is TerminalKind.TIMED_OUT
    assert kinds[order[2]] is TerminalKind.TIMED_OUT
    assert "alice@" not in str(result)
