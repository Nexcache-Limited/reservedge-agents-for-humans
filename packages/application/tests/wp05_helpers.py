from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from fakes import InMemoryApprovalRepository
from test_rework_wp04_r1 import _a2_for, _binding
from wp04_helpers import A2_ID, BUYER, OCCURRED_AT, OWNER, SUPPLIERS

from itaa_application.approval_service import ApprovalService
from itaa_application.dispatch_service import DispatchService
from itaa_application.offer_boundary import AuthorizedResponseBinding, CollectedSupplierResponse
from itaa_application.policy_evaluation import (
    PolicyProfile,
    TrustedEvidence,
    TrustedPolicyEvaluation,
    required_simulator_checks,
)
from itaa_application.supplier_port import TerminalKind
from itaa_domain.identifiers import CorrelationId, IntentId, SupplierToken
from itaa_domain.value_objects import (
    AddOn,
    CancellationTerm,
    EvidenceRef,
    EvidenceType,
    LotType,
    RefundTerm,
    SimulatedAvailability,
    parse_utc,
)
from itaa_ranking.inputs import ReliabilityFact

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "packages" / "contracts" / "fixtures"
JFK = json.loads((FIXTURES / "valid" / "purchase-intent-jfk.json").read_text(encoding="utf-8"))
DEADLINE = parse_utc(JFK["solicitation"]["responseDeadline"], "deadline")
INTENT = IntentId(JFK["intentId"])
CORRELATIONS = (
    CorrelationId("cr_01k2m3n4p5q6r7s8t9v0w1x2m1"),
    CorrelationId("cr_01k2m3n4p5q6r7s8t9v0w1x2m2"),
    CorrelationId("cr_01k2m3n4p5q6r7s8t9v0w1x2m3"),
)

RELIABILITY = (
    ReliabilityFact(
        SUPPLIERS[0],
        700_000,
        EvidenceRef("registry.parkdirect.reliability.v1"),
        "synthetic.v1",
    ),
    ReliabilityFact(
        SUPPLIERS[1],
        950_000,
        EvidenceRef("registry.skyshield.reliability.v1"),
        "synthetic.v1",
    ),
    ReliabilityFact(
        SUPPLIERS[2],
        850_000,
        EvidenceRef("registry.terminalflex.reliability.v1"),
        "synthetic.v1",
    ),
)


def load_offer(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / "valid" / name).read_text(encoding="utf-8"))


def load_invalid_offer(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / "invalid" / name).read_text(encoding="utf-8"))


def clone(payload: dict[str, object]) -> dict[str, object]:
    return deepcopy(payload)


def solicitation_binding():
    return _binding()


def envelope_for(token: SupplierToken):
    return next(item for item in _binding().envelopes if item.assignment.supplier_token == token)


def authorized_binding_for(token: SupplierToken, correlation: CorrelationId | None = None):
    repo = InMemoryApprovalRepository()
    approvals = ApprovalService(repo)
    solicitation = _binding()
    approvals.issue(_a2_for(solicitation))
    index = list(SUPPLIERS).index(token)
    auth = DispatchService(repo).authorize(
        A2_ID,
        binding=solicitation,
        supplier_token=token,
        occurred_at=OCCURRED_AT,
        actor=BUYER,
        owner_id=OWNER,
    )
    return AuthorizedResponseBinding.from_authorization(
        auth,
        correlation_id=correlation or CORRELATIONS[index],
    )


def collected_offer(
    payload: dict[str, object],
    binding: AuthorizedResponseBinding,
    received_at=OCCURRED_AT,
) -> CollectedSupplierResponse:
    return CollectedSupplierResponse.seal(
        supplier_token=binding.supplier_token,
        invitation=binding.invitation,
        correlation_id=binding.correlation_id,
        kind=TerminalKind.OFFER,
        received_at=received_at,
        payload=payload,
        completed_at=received_at,
        binding=binding,
    )


def scoped_fixture(name: str) -> tuple[dict[str, object], AuthorizedResponseBinding]:
    payload = clone(load_offer(name))
    binding = authorized_binding_for(SupplierToken(str(payload["supplierToken"])))
    payload["intentId"] = binding.scoped_intent_id.to_primitive()
    return payload, binding


def fixture_policy(
    binding: AuthorizedResponseBinding, payload: dict[str, object]
) -> TrustedPolicyEvaluation:
    service = payload["service"]
    price = payload["price"]
    add_ons = frozenset(AddOn(str(item)) for item in service["addOns"])
    evidence = tuple(
        TrustedEvidence(EvidenceType(str(item["type"])), EvidenceRef(str(item["ref"])))
        for item in payload["evidence"]
    )
    return TrustedPolicyEvaluation(
        profile=PolicyProfile.CONTRACT_FIXTURE_V1,
        policy_version="contract_fixture_v1",
        supplier_token=binding.supplier_token,
        scoped_intent_id=binding.scoped_intent_id,
        airports=frozenset({binding.airport}),
        vehicles=frozenset({binding.vehicle_class}),
        lot_types=frozenset({LotType(str(service["lotType"]))}),
        add_ons=add_ons,
        allowed_availability=frozenset({SimulatedAvailability(str(service["availability"]))}),
        evidence=evidence,
        floor_minor_per_day=0,
        billable_days=1,
        max_discount_micros=1_000_000,
        allowed_cancellations=frozenset(CancellationTerm),
        allowed_refunds=frozenset(RefundTerm),
        min_validity_seconds=15 * 60,
        max_validity_seconds=48 * 60 * 60,
        fees_minor=int(price["feesMinor"]),
        tax_minor=int(price["taxMinor"]),
        add_on_price_minor=0,
        simulator_only=required_simulator_checks(add_ons),
    )
