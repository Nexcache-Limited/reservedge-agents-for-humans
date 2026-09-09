from __future__ import annotations

from dataclasses import replace

import pytest
from test_envelopes import _recipients
from wp04_helpers import EXPIRES_AT, OCCURRED_AT, RESOURCE_INTENT, load_jfk

from itaa_application.errors import ApplicationError
from itaa_application.supplier_port import ClosedReason, SupplierAttempt, TerminalKind
from itaa_domain.identifiers import CorrelationId, OfferId, SignatureHandle
from itaa_domain.value_objects import JS_SAFE_MAX, RefundTerm, Version, parse_utc
from itaa_policy.disclosure import DisclosurePurpose
from itaa_policy.envelopes import bind_solicitation
from itaa_supplier_simulator.economics import billable_days
from itaa_supplier_simulator.engine import SimulatedSupplier
from itaa_supplier_simulator.harness import seeded_ports
from itaa_supplier_simulator.policy import PARKDIRECT, SKYSHIELD, TERMINALFLEX, SimulatedPolicy

ATTEMPT_IDS = (
    (OfferId("of_01k2m3n4p5q6r7s8t9v0w1x2a4"), SignatureHandle("sg_01k2m3n4p5q6r7s8t9v0w1x2h4")),
    (OfferId("of_01k2m3n4p5q6r7s8t9v0w1x2a5"), SignatureHandle("sg_01k2m3n4p5q6r7s8t9v0w1x2h5")),
    (OfferId("of_01k2m3n4p5q6r7s8t9v0w1x2a6"), SignatureHandle("sg_01k2m3n4p5q6r7s8t9v0w1x2h6")),
)
CORRELATIONS = (
    CorrelationId("cr_01k2m3n4p5q6r7s8t9v0w1x2m1"),
    CorrelationId("cr_01k2m3n4p5q6r7s8t9v0w1x2m2"),
    CorrelationId("cr_01k2m3n4p5q6r7s8t9v0w1x2m3"),
)


def _attempts() -> list[SupplierAttempt]:
    binding = bind_solicitation(
        load_jfk(),
        intent_resource_id=RESOURCE_INTENT,
        intent_resource_version=Version(2),
        purpose=DisclosurePurpose.PURCHASE_INTENT_DISPATCH,
        expires_at=EXPIRES_AT,
        recipients=_recipients(),
    )
    by_token = {item.assignment.supplier_token: item for item in binding.envelopes}
    attempts: list[SupplierAttempt] = []
    for index, policy in enumerate((PARKDIRECT, SKYSHIELD, TERMINALFLEX)):
        offer_id, signature = ATTEMPT_IDS[index]
        envelope = by_token[policy.supplier_token]
        attempts.append(
            SupplierAttempt(
                envelope=envelope,
                occurred_at=OCCURRED_AT,
                deadline=EXPIRES_AT,
                invitation=envelope.assignment.invitation,
                offer_id=offer_id,
                signature=signature,
                correlation_id=CORRELATIONS[index],
            )
        )
    return attempts


def test_each_seeded_supplier_emits_a_simulated_offer() -> None:
    for policy, attempt in zip((PARKDIRECT, SKYSHIELD, TERMINALFLEX), _attempts(), strict=True):
        supplier = SimulatedSupplier(policy)
        before = supplier.remaining_capacity
        result = supplier.attempt(attempt)
        assert result.kind is TerminalKind.OFFER
        assert result.payload is not None
        assert result.payload["simulation"] is True
        assert str(result.payload["service"]["availability"]).endswith("_simulated")
        window = attempt.envelope.payload_dict()["serviceWindow"]
        days = billable_days(parse_utc(window["start"], "s"), parse_utc(window["end"], "e"))
        assert result.payload["price"]["subtotalMinor"] - policy.add_on_price_minor >= (
            policy.floor_minor_per_day * days
        )
        assert supplier.remaining_capacity == before - 1


def test_same_seed_is_deterministic() -> None:
    first = SimulatedSupplier(PARKDIRECT).attempt(_attempts()[0])
    second = SimulatedSupplier(PARKDIRECT).attempt(_attempts()[0])
    assert first.payload == second.payload


def test_unsupported_airport_and_vehicle_decline_without_echo() -> None:
    attempt = _attempts()[0]
    closed = replace(PARKDIRECT, airports=frozenset({"LAX"}))
    result = SimulatedSupplier(closed).attempt(attempt)
    assert result.kind is TerminalKind.DECLINED
    assert result.reason is ClosedReason.UNSUPPORTED_AIRPORT
    assert result.payload is None
    assert "LAX" not in str(result)
    assert "JFK" not in str(result)


def test_zero_capacity_declines() -> None:
    result = SimulatedSupplier(PARKDIRECT, remaining_capacity=0).attempt(_attempts()[0])
    assert result.kind is TerminalKind.DECLINED
    assert result.reason is ClosedReason.INSUFFICIENT_CAPACITY


def test_discount_and_floor_boundaries() -> None:
    attempt = _attempts()[0]
    with pytest.raises(ApplicationError, match="discount_micros: out_of_range"):
        replace(PARKDIRECT, discount_micros=100_001, max_discount_micros=100_000)
    with pytest.raises(ApplicationError, match="list_minor_per_day: below_floor"):
        replace(PARKDIRECT, list_minor_per_day=1000, discount_micros=0)
    exact_floor = replace(
        PARKDIRECT, list_minor_per_day=1700, discount_micros=0, demand_micros=1_000_000
    )
    offered = SimulatedSupplier(exact_floor).attempt(attempt)
    assert offered.kind is TerminalKind.OFFER


def test_loss_making_addon_and_invalid_cancellation_pair() -> None:
    with pytest.raises(ApplicationError, match="add_on_margin: non_positive"):
        replace(SKYSHIELD, add_on_price_minor=100, add_on_cost_minor=800)
    with pytest.raises(ApplicationError, match="refund: invalid_pair"):
        replace(SKYSHIELD, refund=RefundTerm.NONE)


def test_malformed_policy_fields_fail_at_construction() -> None:
    with pytest.raises(ApplicationError, match="fees_minor: out_of_range"):
        replace(PARKDIRECT, fees_minor=-1)
    with pytest.raises(ApplicationError, match="fees_minor: must_be_integer"):
        replace(PARKDIRECT, fees_minor=1.5)  # type: ignore[arg-type]
    with pytest.raises(ApplicationError, match="fees_minor: must_be_integer"):
        replace(PARKDIRECT, fees_minor=True)  # type: ignore[arg-type]
    with pytest.raises(ApplicationError, match="fees_minor: out_of_range"):
        replace(PARKDIRECT, fees_minor=JS_SAFE_MAX + 1)
    with pytest.raises(ApplicationError, match="airports: required"):
        replace(PARKDIRECT, airports=frozenset())
    with pytest.raises(ApplicationError, match="demand_micros: out_of_range"):
        replace(PARKDIRECT, demand_micros=10_000_001)
    with pytest.raises(ApplicationError, match="validity: invalid"):
        replace(PARKDIRECT, validity_seconds=1)
    with pytest.raises(ApplicationError, match="shuttle_minutes: out_of_range"):
        replace(PARKDIRECT, shuttle_minutes=-1)
    with pytest.raises(ApplicationError, match="distance_metres: out_of_range"):
        replace(PARKDIRECT, distance_metres=100_001)
    with pytest.raises(ApplicationError, match="availability: invalid_enum"):
        replace(PARKDIRECT, availability="confirmed")
    with pytest.raises(ApplicationError, match="remaining_capacity: out_of_range"):
        SimulatedSupplier(PARKDIRECT, remaining_capacity=-1)


def test_invalid_generated_payload_does_not_decrement_capacity() -> None:
    huge = replace(PARKDIRECT, fees_minor=JS_SAFE_MAX)
    supplier = SimulatedSupplier(huge)
    before = supplier.remaining_capacity
    with pytest.raises(ApplicationError, match="totalMinor: overflow"):
        supplier.attempt(_attempts()[0])
    assert supplier.remaining_capacity == before


def test_seeded_ports_are_distinct_contexts() -> None:
    ports = seeded_ports()
    assert len(ports) == 3
    assert len(set(map(id, ports.values()))) == 3


def test_policy_type_is_simulated_policy() -> None:
    assert type(PARKDIRECT) is SimulatedPolicy
