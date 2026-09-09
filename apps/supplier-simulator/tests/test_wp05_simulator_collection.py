from __future__ import annotations

from itertools import permutations

from fakes import InMemoryApprovalRepository
from test_rework_wp04_r1 import _a2_for, _binding
from wp04_helpers import A2_ID, BUYER, EXPIRES_AT, OCCURRED_AT, OWNER, SUPPLIERS

from itaa_application.approval_service import ApprovalService
from itaa_application.dispatch_service import DispatchService
from itaa_application.solicitation_service import SolicitationCollector, SolicitationSlot
from itaa_application.supplier_port import FrozenClock, TerminalKind
from itaa_domain.identifiers import CorrelationId, OfferId, SignatureHandle
from itaa_supplier_simulator.harness import seeded_ports

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


def test_seeded_simulators_collect_three_simulated_offers() -> None:
    repo = InMemoryApprovalRepository()
    approvals = ApprovalService(repo)
    binding = _binding()
    approvals.issue(_a2_for(binding))
    collector = SolicitationCollector(DispatchService(repo))
    first = None
    for _order in permutations(SUPPLIERS):
        result = collector.collect(
            approval_id=A2_ID,
            binding=binding,
            slots=SLOTS,
            ports=seeded_ports(),
            deadline=EXPIRES_AT,
            actor=BUYER,
            owner_id=OWNER,
            clock=FrozenClock(OCCURRED_AT),
        )
        assert [item.kind for item in result.terminals] == [TerminalKind.OFFER] * 3
        for terminal in result.terminals:
            assert terminal.payload is not None
            assert terminal.payload["simulation"] is True
        snapshot = tuple(
            (item.supplier_token.to_primitive(), item.payload["price"]["totalMinor"])
            for item in result.terminals
        )
        if first is None:
            first = snapshot
        assert snapshot == first
