from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from types import MappingProxyType

import pytest
from test_approvals import _a1, _a2, _a3, _a4, _request_from
from test_rework_wp04_r1 import _a2_for, _binding
from wp04_helpers import (
    ACCEPTANCE_ID,
    BUYER,
    EXPIRES_AT,
    INVITATIONS,
    OCCURRED_AT,
    OFFER_ID,
    OWNER,
    PLACEHOLDER_HASH,
    RESOURCE_INTENT,
    SCOPED_INTENTS,
    SUPPLIERS,
)

from itaa_domain.value_objects import AuthorizationAction, AuthorizationMode, Version
from itaa_policy.approvals import ApprovalDenyReason, validate_approval
from itaa_policy.envelopes import authorize_dispatch
from itaa_policy.errors import PolicyError
from itaa_policy.isolation import SupplierCapability, SupplierPrincipal


def test_mismatched_assignment_and_scope_cannot_be_constructed() -> None:
    envelope = _binding().envelopes[0]
    tampered = replace(envelope.scope, principal=SupplierPrincipal(SUPPLIERS[1]))
    with pytest.raises(PolicyError, match="assignment_scope_mismatch") as captured:
        replace(envelope, scope=tampered)
    assert "sp_" not in str(captured.value)
    assert SUPPLIERS[0].to_primitive() not in str(captured.value)
    assert SUPPLIERS[1].to_primitive() not in str(captured.value)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda scope: replace(scope, principal=SupplierPrincipal(SUPPLIERS[1])),
        lambda scope: replace(scope, invitation=INVITATIONS[1]),
        lambda scope: replace(scope, intent_id=SCOPED_INTENTS[1]),
        lambda scope: replace(scope, valid_until=scope.valid_until + timedelta(minutes=1)),
        lambda scope: replace(scope, capabilities=frozenset({SupplierCapability.INVITATION_READ})),
    ],
)
def test_assignment_scope_mismatches_cannot_authorize(mutator) -> None:
    binding = _binding()
    grant = _a2_for(binding)
    envelope = binding.envelopes[0]
    object.__setattr__(envelope, "scope", mutator(envelope.scope))
    with pytest.raises(PolicyError, match="assignment_scope_mismatch") as captured:
        authorize_dispatch(
            grant,
            binding=binding,
            supplier_token=SUPPLIERS[0],
            occurred_at=OCCURRED_AT,
            actor=BUYER,
            owner_id=OWNER,
        )
    assert "sp_" not in str(captured.value)
    assert "alice@" not in str(captured.value)


def test_payload_alias_mismatch_cannot_be_constructed() -> None:
    envelope = _binding().envelopes[0]
    payload = dict(envelope.payload)
    payload["intentId"] = SCOPED_INTENTS[1].to_primitive()
    with pytest.raises(PolicyError, match="payload_mismatch") as captured:
        replace(envelope, payload=MappingProxyType(payload))
    assert SCOPED_INTENTS[1].to_primitive() not in str(captured.value)


def test_consistent_listed_supplier_still_authorizes() -> None:
    binding = _binding()
    authorized = authorize_dispatch(
        _a2_for(binding),
        binding=binding,
        supplier_token=SUPPLIERS[0],
        occurred_at=OCCURRED_AT,
        actor=BUYER,
        owner_id=OWNER,
    )
    assert authorized.allowed is True
    assert authorized.envelope is not None
    assert authorized.envelope.assignment.supplier_token == SUPPLIERS[0]
    assert authorized.envelope.scope.principal.supplier_token == SUPPLIERS[0]


def test_a1_request_with_a4_fields_cannot_be_constructed() -> None:
    with pytest.raises(PolicyError, match="a4_fields") as captured:
        replace(
            _request_from(_a1()),
            amount_minor=11900,
            currency="USD",
            supplier_token=SUPPLIERS[0],
        )
    assert captured.value.code == "must_be_absent"
    assert "11900" not in str(captured.value)
    assert "USD" not in str(captured.value)


@pytest.mark.parametrize(
    ("grant_factory", "changes", "code"),
    [
        (_a1, {"content_hash": PLACEHOLDER_HASH, "manifest_hash": PLACEHOLDER_HASH}, "a2_fields"),
        (_a1, {"recipient_count": 1, "solicitation_expires_at": EXPIRES_AT}, "a2_fields"),
        (_a1, {"intent_id": RESOURCE_INTENT}, "intent_id"),
        (_a1, {"offer_id": OFFER_ID, "offer_version": Version(1)}, "a3_fields"),
        (_a1, {"terms_hash": PLACEHOLDER_HASH, "offer_valid_until": EXPIRES_AT}, "a3_fields"),
        (_a1, {"acceptance_id": ACCEPTANCE_ID, "request_hash": PLACEHOLDER_HASH}, "a4_fields"),
        (
            _a1,
            {
                "action": AuthorizationAction.RESERVE_PARKING,
                "mode": AuthorizationMode.SIMULATED,
                "decision_expires_at": EXPIRES_AT,
            },
            "a4_fields",
        ),
        (_a2, {"intent_id": RESOURCE_INTENT}, "intent_id"),
        (_a2, {"offer_id": OFFER_ID, "offer_version": Version(1)}, "a3_fields"),
        (_a2, {"amount_minor": 11900, "currency": "USD"}, "a4_fields"),
        (_a3, {"content_hash": PLACEHOLDER_HASH, "manifest_hash": PLACEHOLDER_HASH}, "a2_fields"),
        (
            _a3,
            {"amount_minor": 11900, "currency": "USD", "supplier_token": SUPPLIERS[0]},
            "a4_fields",
        ),
        (_a4, {"content_hash": PLACEHOLDER_HASH, "manifest_hash": PLACEHOLDER_HASH}, "a2_fields"),
        (_a4, {"intent_id": RESOURCE_INTENT}, "intent_id"),
        (_a4, {"offer_id": OFFER_ID, "terms_hash": PLACEHOLDER_HASH}, "a3_fields"),
    ],
)
def test_cross_kind_request_fields_are_rejected(
    grant_factory, changes: dict[str, object], code: str
) -> None:
    request = _request_from(grant_factory())
    with pytest.raises(PolicyError) as captured:
        replace(request, **changes)
    assert captured.value.code in {code, "must_be_absent"}
    assert captured.value.field in {code, "a2_fields", "a3_fields", "a4_fields", "intent_id"}
    assert "alice@" not in str(captured.value)


def test_valid_kind_exact_requests_still_allow() -> None:
    for grant in (_a1(), _a2(), _a3(), _a4()):
        decision = validate_approval(grant, _request_from(grant))
        assert decision.allowed is True
        assert decision.reason is ApprovalDenyReason.ALLOWED
