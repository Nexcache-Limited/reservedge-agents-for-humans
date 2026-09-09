from __future__ import annotations

from dataclasses import replace

import pytest
from wp04_helpers import EXPIRES_AT, INVITATIONS, OCCURRED_AT
from wp05_helpers import fixture_policy, scoped_fixture

from itaa_application.errors import ApplicationError
from itaa_application.policy_evaluation import PolicyProfile
from itaa_application.supplier_port import FrozenClock, SupplierAttempt
from itaa_domain.identifiers import OfferId, SignatureHandle


def test_policy_construction_rejects_invalid_fields() -> None:
    payload, binding = scoped_fixture("offer-parkdirect.json")
    policy = fixture_policy(binding, payload)
    with pytest.raises(ApplicationError, match="billable_days: must_be_positive"):
        replace(policy, billable_days=0)
    with pytest.raises(ApplicationError, match="floor_minor_per_day: out_of_range"):
        replace(policy, floor_minor_per_day=-1)
    with pytest.raises(ApplicationError, match="max_discount_micros: out_of_range"):
        replace(policy, max_discount_micros=1_000_001)
    with pytest.raises(ApplicationError, match="profile: invalid_enum"):
        replace(policy, profile="simulator_v1")  # type: ignore[arg-type]
    with pytest.raises(ApplicationError, match="airports: required"):
        replace(policy, airports=frozenset())
    with pytest.raises(ApplicationError, match="vehicles: required"):
        replace(policy, vehicles=frozenset())
    with pytest.raises(ApplicationError, match="lot_types: required"):
        replace(policy, lot_types=frozenset())
    with pytest.raises(ApplicationError, match="allowed_availability: required"):
        replace(policy, allowed_availability=frozenset())
    with pytest.raises(ApplicationError, match="evidence: required"):
        replace(policy, evidence=())
    with pytest.raises(ApplicationError, match="allowed_cancellations: required"):
        replace(policy, allowed_cancellations=frozenset())
    with pytest.raises(ApplicationError, match="allowed_refunds: required"):
        replace(policy, allowed_refunds=frozenset())
    assert policy.profile is PolicyProfile.CONTRACT_FIXTURE_V1


def test_clock_and_attempt_invitation_guard() -> None:
    clock = FrozenClock(OCCURRED_AT)
    clock.advance(EXPIRES_AT - OCCURRED_AT)
    assert clock.now() == EXPIRES_AT
    payload, binding = scoped_fixture("offer-parkdirect.json")
    with pytest.raises(ApplicationError, match="invitation: required"):
        SupplierAttempt(
            envelope=binding.envelope,
            occurred_at=OCCURRED_AT,
            deadline=EXPIRES_AT,
            invitation=object(),  # type: ignore[arg-type]
            offer_id=OfferId(str(payload["offerId"])),
            signature=SignatureHandle(str(payload["signature"])),
            correlation_id=binding.correlation_id,
        )
    with pytest.raises(ApplicationError, match="invitation: wrong_channel"):
        SupplierAttempt(
            envelope=binding.envelope,
            occurred_at=OCCURRED_AT,
            deadline=EXPIRES_AT,
            invitation=INVITATIONS[1] if binding.invitation == INVITATIONS[0] else INVITATIONS[0],
            offer_id=OfferId(str(payload["offerId"])),
            signature=SignatureHandle(str(payload["signature"])),
            correlation_id=binding.correlation_id,
        )
