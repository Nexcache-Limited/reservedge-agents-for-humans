from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from inspect import signature

import pytest
from test_wp05_solicitation import ConstantPort, _collect, _collector, fake_ports
from wp04_helpers import EXPIRES_AT, INVITATIONS, OCCURRED_AT, SUPPLIERS
from wp05_helpers import (
    collected_offer,
    fixture_policy,
    scoped_fixture,
)
from wp05_ranking_helpers import (
    EVALUATED_AT,
    VALID_FROM,
    VALID_UNTIL,
    _need,
    _reliability,
    parkdirect_offer,
    rank_golden,
    skyshield_offer,
    terminalflex_offer,
)

from itaa_application.errors import ApplicationError
from itaa_application.offer_boundary import (
    AuthorizedResponseBinding,
    CollectedSupplierResponse,
    accept_offer,
)
from itaa_application.policy_evaluation import SimulatorOnlyCheck, required_simulator_checks
from itaa_application.ranking_decision import decide
from itaa_application.supplier_port import ClosedReason, FrozenClock, SupplierTerminal, TerminalKind
from itaa_domain.offer import OfferState
from itaa_domain.value_objects import AddOn, EvidenceRef, SimulatedAvailability
from itaa_policy.approvals import ApprovalDecision, ApprovalDenyReason
from itaa_policy.canonical import SEPARATOR_RANKING_DECISION, hash_canonical
from itaa_policy.envelopes import DispatchAuthorization
from itaa_ranking.errors import RankingError
from itaa_ranking.inputs import ReliabilityFact
from itaa_ranking.profile import DEFAULT_PROFILE, DEFAULT_WEIGHTS, RankingProfile
from itaa_ranking.rank import rank_offers
from itaa_ranking.vocab import ExclusionCode, ExclusionField, ProfileReason


def test_direct_construction_and_replace_are_sealed() -> None:
    payload, binding = scoped_fixture("offer-parkdirect.json")
    with pytest.raises(ApplicationError, match="binding: sealed"):
        AuthorizedResponseBinding()
    with pytest.raises(ApplicationError, match="response: sealed"):
        CollectedSupplierResponse()
    with pytest.raises(ApplicationError, match="binding: sealed"):
        replace(binding, correlation_id=binding.correlation_id)
    for field in (
        "airport",
        "currency",
        "covered",
        "vehicle_class",
        "response_deadline",
        "disclosure_hash",
        "representable_add_ons",
        "shuttle_max_minutes",
        "disclosure_profile",
    ):
        with pytest.raises(ApplicationError, match="binding: sealed"):
            replace(binding, **{field: None})
    denied = DispatchAuthorization(
        False,
        ApprovalDecision(False, ApprovalDenyReason.INACTIVE, None, None),
        None,
    )
    with pytest.raises(ApplicationError, match="authorization: denied"):
        AuthorizedResponseBinding.from_authorization(denied, correlation_id=binding.correlation_id)
    assert binding.currency == "USD"
    assert binding.vehicle_class == "standard"
    assert binding.disclosure_hash.value.startswith("sha256:")
    assert binding.payload_expires_at == binding.envelope_expires_at
    mapped = accept_offer(
        collected_offer(payload, binding),
        fixture_policy(binding, payload),
        evaluated_at=OCCURRED_AT,
    )
    assert mapped.offer.state is OfferState.ELIGIBLE


def test_accept_offer_rejects_detached_payload_and_channel() -> None:
    payload, binding = scoped_fixture("offer-parkdirect.json")
    policy = fixture_policy(binding, payload)
    names = signature(accept_offer).parameters
    assert "payload" not in names
    assert "received_at" not in names
    assert "binding" not in names
    with pytest.raises(TypeError):
        accept_offer(  # type: ignore[misc]
            payload,
            binding,
            policy,
            received_at=OCCURRED_AT,
            evaluated_at=OCCURRED_AT,
        )
    declined = CollectedSupplierResponse.seal(
        supplier_token=binding.supplier_token,
        invitation=binding.invitation,
        correlation_id=binding.correlation_id,
        kind=TerminalKind.DECLINED,
        received_at=OCCURRED_AT,
        reason=ClosedReason.INSUFFICIENT_CAPACITY,
        binding=binding,
    )
    with pytest.raises(ApplicationError, match="kind: not_offer"):
        accept_offer(declined, policy, evaluated_at=OCCURRED_AT)
    foreign = scoped_fixture("offer-skyshield.json")[1]
    with pytest.raises(ApplicationError, match="correlation_id: mismatch"):
        CollectedSupplierResponse.seal(
            supplier_token=binding.supplier_token,
            invitation=binding.invitation,
            correlation_id=foreign.correlation_id,
            kind=TerminalKind.OFFER,
            received_at=OCCURRED_AT,
            payload=payload,
            binding=binding,
        )


def test_port_exception_and_wrong_channel_preserve_other_suppliers() -> None:
    collector, binding, _repo = _collector()

    class Boom:
        def attempt(self, request):
            raise RuntimeError("alice@example.com")

    class WrongInvite:
        def attempt(self, request):
            other = INVITATIONS[1] if request.invitation == INVITATIONS[0] else INVITATIONS[0]
            token = request.envelope.assignment.supplier_token
            return SupplierTerminal(
                TerminalKind.OFFER,
                token,
                request.correlation_id,
                other,
                request.occurred_at,
                payload={"simulation": True, "supplierToken": token.to_primitive()},
            )

    ports = fake_ports()
    ports[SUPPLIERS[0]] = Boom()
    result = _collect(collector, binding, ports)
    kinds = {item.supplier_token: item.kind for item in result.terminals}
    assert kinds[SUPPLIERS[0]] is TerminalKind.FAILED
    assert kinds[SUPPLIERS[1]] is TerminalKind.OFFER
    assert kinds[SUPPLIERS[2]] is TerminalKind.OFFER
    haystack = str(result).lower()
    assert "alice@" not in haystack
    assert "example.com" not in haystack
    ports = fake_ports()
    ports[SUPPLIERS[0]] = WrongInvite()
    result = _collect(collector, binding, ports)
    kinds = {item.supplier_token: item.kind for item in result.terminals}
    assert kinds[SUPPLIERS[0]] is TerminalKind.INVALID
    assert kinds[SUPPLIERS[1]] is TerminalKind.OFFER
    assert kinds[SUPPLIERS[2]] is TerminalKind.OFFER


def test_mutating_supplier_payload_after_collection_is_isolated() -> None:
    collector, binding, _repo = _collector()
    original = {"simulation": True, "nested": {"totalMinor": 1}, "supplierToken": "x"}

    class MutablePort:
        def attempt(self, request):
            token = request.envelope.assignment.supplier_token
            original["supplierToken"] = token.to_primitive()
            return SupplierTerminal(
                TerminalKind.OFFER,
                token,
                request.correlation_id,
                request.invitation,
                request.occurred_at,
                payload=original,
            )

    result = _collect(
        collector, binding, {token: MutablePort() for token in SUPPLIERS}, FrozenClock(OCCURRED_AT)
    )
    original["nested"]["totalMinor"] = 999
    original["simulation"] = False
    for item in result.terminals:
        assert item.kind is TerminalKind.OFFER
        assert item.payload is not None
        assert item.payload["simulation"] is True
        assert item.payload["nested"]["totalMinor"] == 1
        with pytest.raises(TypeError):
            item.payload["simulation"] = False  # type: ignore[index]


def test_unallowed_addon_fees_evidence_vehicle_and_attestation_fail() -> None:
    payload, binding = scoped_fixture("offer-parkdirect.json")
    policy = fixture_policy(binding, payload)
    mutated = scoped_fixture("offer-parkdirect.json")[0]
    mutated["service"]["addOns"] = [AddOn.EV_CHARGING.value]
    with pytest.raises(ApplicationError, match="addOns: unsupported"):
        accept_offer(collected_offer(mutated, binding), policy, evaluated_at=OCCURRED_AT)
    mutated = scoped_fixture("offer-parkdirect.json")[0]
    mutated["price"]["feesMinor"] = int(mutated["price"]["feesMinor"]) + 777
    mutated["price"]["totalMinor"] = int(mutated["price"]["totalMinor"]) + 777
    with pytest.raises(ApplicationError, match="feesMinor: mismatch"):
        accept_offer(collected_offer(mutated, binding), policy, evaluated_at=OCCURRED_AT)
    mutated = scoped_fixture("offer-parkdirect.json")[0]
    mutated["price"]["taxMinor"] = int(mutated["price"]["taxMinor"]) + 1
    mutated["price"]["totalMinor"] = int(mutated["price"]["totalMinor"]) + 1
    with pytest.raises(ApplicationError, match="taxMinor: mismatch"):
        accept_offer(collected_offer(mutated, binding), policy, evaluated_at=OCCURRED_AT)
    mutated = scoped_fixture("offer-parkdirect.json")[0]
    mutated["evidence"] = [{"type": "supplier_policy", "ref": "policy.attacker.v1"}]
    with pytest.raises(ApplicationError, match="evidence: mismatch"):
        accept_offer(collected_offer(mutated, binding), policy, evaluated_at=OCCURRED_AT)
    mutated = scoped_fixture("offer-parkdirect.json")[0]
    mutated["service"]["availability"] = SimulatedAvailability.LIMITED_SIMULATED.value
    with pytest.raises(ApplicationError, match="availability: unsupported"):
        accept_offer(collected_offer(mutated, binding), policy, evaluated_at=OCCURRED_AT)
    mutated = scoped_fixture("offer-parkdirect.json")[0]
    mutated["service"]["lotType"] = "garage"
    with pytest.raises(ApplicationError, match="lotType: unsupported"):
        accept_offer(collected_offer(mutated, binding), policy, evaluated_at=OCCURRED_AT)
    with pytest.raises(ApplicationError, match="vehicleClass: unsupported"):
        accept_offer(
            collected_offer(payload, binding),
            replace(policy, vehicles=frozenset({"compact"})),
            evaluated_at=OCCURRED_AT,
        )
    with pytest.raises(ApplicationError, match="simulator_only: incomplete"):
        replace(policy, simulator_only=frozenset())
    with pytest.raises(ApplicationError, match="simulator_only: incomplete"):
        replace(
            policy,
            simulator_only=required_simulator_checks(frozenset())
            - {SimulatorOnlyCheck.DISCOUNT_CAP},
        )
    with pytest.raises(ApplicationError) as captured:
        replace(policy, policy_version="alice@example.com")
    assert "alice@" not in str(captured.value)


def test_snapshot_is_immutable_and_fingerprint_recomputes() -> None:
    result = rank_golden()
    with pytest.raises((TypeError, FrozenInstanceError)):
        result.input_snapshot.profile_id = "tampered"  # type: ignore[misc]
    primitive = result.input_snapshot.to_primitive()
    primitive["profileId"] = "tampered"
    primitive["offers"][0]["addOns"].append("ev_charging")
    assert result.input_snapshot.profile_id == "airport_parking_v1"
    assert "ev_charging" not in result.input_snapshot.offers[0].add_ons
    decision = decide(
        (parkdirect_offer(), skyshield_offer(), terminalflex_offer()),
        _need(),
        evaluated_at=EVALUATED_AT,
        reliability=_reliability(),
    )
    recomputed = hash_canonical(
        SEPARATOR_RANKING_DECISION, decision.result.input_snapshot.to_primitive()
    )
    assert recomputed == decision.fingerprint
    copy = decision.result.fingerprint_material()
    copy["profileId"] = "tampered"
    assert (
        hash_canonical(SEPARATOR_RANKING_DECISION, decision.result.input_snapshot.to_primitive())
        == decision.fingerprint
    )


def test_identity_text_is_rejected_from_profile_reliability_and_policy() -> None:
    with pytest.raises(RankingError) as captured:
        RankingProfile(
            profile_id="airport_parking_v1",
            profile_version="1.0",
            weight_version="1.0",
            weights=dict(DEFAULT_WEIGHTS),
            reason="alice@example.com",  # type: ignore[arg-type]
            evidence_ref=EvidenceRef("ranking.airport_parking_v1.weights"),
        )
    assert "alice@" not in str(captured.value)
    with pytest.raises(RankingError) as captured:
        ReliabilityFact(
            SUPPLIERS[0],
            700_000,
            EvidenceRef("registry.parkdirect.reliability.v1"),
            "alice@example.com",
        )
    assert "alice@" not in str(captured.value)
    assert DEFAULT_PROFILE.reason is ProfileReason.LOCKED_MVP_DEFAULT


def test_temporal_eligibility_boundaries() -> None:
    before = rank_offers(
        (replace(parkdirect_offer(), valid_from=EVALUATED_AT + timedelta(microseconds=1)),),
        _need(),
        evaluated_at=EVALUATED_AT,
        reliability=_reliability(),
    )
    assert before.ranked == ()
    assert before.exclusions[0].field is ExclusionField.VALID_FROM
    assert before.exclusions[0].code is ExclusionCode.NOT_YET_VALID
    at_from = rank_offers(
        (parkdirect_offer(),),
        _need(),
        evaluated_at=VALID_FROM,
        reliability=_reliability(),
    )
    assert at_from.ranked[0].offer_id == parkdirect_offer().offer_id
    at_until = rank_offers(
        (parkdirect_offer(),),
        _need(),
        evaluated_at=VALID_UNTIL,
        reliability=_reliability(),
    )
    assert at_until.ranked == ()
    assert at_until.exclusions[0].code is ExclusionCode.EXPIRED
    payload, binding = scoped_fixture("offer-parkdirect.json")
    payload["validFrom"] = "2026-08-20T16:00:01Z"
    with pytest.raises(ApplicationError, match="validFrom: future"):
        accept_offer(
            collected_offer(payload, binding, OCCURRED_AT),
            fixture_policy(binding, payload),
            evaluated_at=OCCURRED_AT,
        )
    payload, binding = scoped_fixture("offer-parkdirect.json")
    with pytest.raises(ApplicationError, match="validFrom: not_yet_valid"):
        accept_offer(
            collected_offer(payload, binding),
            fixture_policy(binding, payload),
            evaluated_at=OCCURRED_AT - timedelta(microseconds=1),
        )


def test_golden_scores_remain_locked() -> None:
    result = rank_golden()
    assert [item.score_micros for item in result.ranked] == [671_000, 660_000, 535_000]


def test_declined_at_deadline_via_buyer_clock_is_late() -> None:
    collector, binding, _repo = _collector()
    clock = FrozenClock(OCCURRED_AT)

    class AdvanceDecline:
        def attempt(self, request):
            result = ConstantPort(
                TerminalKind.DECLINED, ClosedReason.INSUFFICIENT_CAPACITY
            ).attempt(request)
            clock.set(EXPIRES_AT)
            return result

    ports = fake_ports()
    ports[SUPPLIERS[0]] = AdvanceDecline()
    result = _collect(collector, binding, ports, clock)
    kinds = {item.supplier_token: item.kind for item in result.terminals}
    assert kinds[SUPPLIERS[0]] is TerminalKind.LATE
    assert all(item.payload is None for item in result.terminals if item.kind is TerminalKind.LATE)
