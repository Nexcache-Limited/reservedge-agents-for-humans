from __future__ import annotations

from dataclasses import replace

import pytest
from wp04_helpers import OCCURRED_AT, SUPPLIERS
from wp05_helpers import (
    authorized_binding_for,
    collected_offer,
    envelope_for,
    fixture_policy,
    scoped_fixture,
)

from itaa_application.errors import ApplicationError
from itaa_application.offer_boundary import AuthorizedResponseBinding, accept_offer
from itaa_domain.identifiers import CorrelationId
from itaa_domain.offer import OfferState
from itaa_policy.approvals import ApprovalDecision, ApprovalDenyReason
from itaa_policy.envelopes import DispatchAuthorization


def test_absent_and_foreign_invitation_fail_closed() -> None:
    payload, binding = scoped_fixture("offer-parkdirect.json")
    with pytest.raises(ApplicationError, match="response: required"):
        accept_offer(
            None,  # type: ignore[arg-type]
            fixture_policy(binding, payload),
            evaluated_at=OCCURRED_AT,
        )
    foreign = authorized_binding_for(SUPPLIERS[1])
    with pytest.raises(ApplicationError, match="supplierToken: mismatch"):
        accept_offer(
            collected_offer(payload, foreign),
            fixture_policy(foreign, payload),
            evaluated_at=OCCURRED_AT,
        )
    with pytest.raises(ApplicationError, match="binding: sealed"):
        replace(binding, invitation=foreign.invitation)
    with pytest.raises(ApplicationError, match="binding: sealed"):
        replace(binding, scoped_intent_id=foreign.scoped_intent_id)


def test_lax_cannot_override_jfk_envelope_airport() -> None:
    binding = authorized_binding_for(SUPPLIERS[0])
    assert binding.airport == "JFK"
    with pytest.raises(ApplicationError, match="binding: sealed"):
        replace(binding, airport="LAX")
    payload, _unused = scoped_fixture("offer-parkdirect.json")
    lax_policy = replace(fixture_policy(binding, payload), airports=frozenset({"LAX"}))
    with pytest.raises(ApplicationError, match="airport: unsupported"):
        accept_offer(
            collected_offer(payload, binding),
            lax_policy,
            evaluated_at=OCCURRED_AT,
        )


def test_policy_evidence_absent_cannot_mark_eligible() -> None:
    payload, binding = scoped_fixture("offer-parkdirect.json")
    with pytest.raises(TypeError):
        accept_offer(  # type: ignore[misc]
            collected_offer(payload, binding),
            evaluated_at=OCCURRED_AT,
        )
    with pytest.raises(ApplicationError, match="policy: required"):
        accept_offer(
            collected_offer(payload, binding),
            None,  # type: ignore[arg-type]
            evaluated_at=OCCURRED_AT,
        )


def test_cross_envelope_supplier_a_on_invitation_b_fails() -> None:
    payload, _park = scoped_fixture("offer-parkdirect.json")
    sky = authorized_binding_for(SUPPLIERS[1])
    with pytest.raises(ApplicationError) as captured:
        accept_offer(
            collected_offer(payload, sky),
            fixture_policy(sky, payload),
            evaluated_at=OCCURRED_AT,
        )
    assert "iv_" not in str(captured.value)
    assert "sp_" not in str(captured.value)
    assert captured.value.code in {"mismatch", "wrong_channel"}


def test_binding_requires_successful_authorization() -> None:
    envelope = envelope_for(SUPPLIERS[0])
    denied = DispatchAuthorization(
        False,
        ApprovalDecision(False, ApprovalDenyReason.INACTIVE, None, None),
        None,
    )
    with pytest.raises(ApplicationError, match="authorization: denied"):
        AuthorizedResponseBinding.from_authorization(
            denied,
            correlation_id=CorrelationId("cr_01k2m3n4p5q6r7s8t9v0w1x2m1"),
        )
    with pytest.raises(ApplicationError, match="binding: sealed"):
        AuthorizedResponseBinding(
            authorization=denied,  # type: ignore[call-arg]
            correlation_id=CorrelationId("cr_01k2m3n4p5q6r7s8t9v0w1x2m1"),
        )
    binding = authorized_binding_for(SUPPLIERS[0])
    assert binding.supplier_token == envelope.assignment.supplier_token
    assert binding.invitation == envelope.assignment.invitation
    assert binding.scoped_intent_id == envelope.assignment.scoped_intent_id
    assert binding.airport == "JFK"
    payload, _unused = scoped_fixture("offer-parkdirect.json")
    mapped = accept_offer(
        collected_offer(payload, binding),
        fixture_policy(binding, payload),
        evaluated_at=OCCURRED_AT,
    )
    assert mapped.offer.state is OfferState.ELIGIBLE
