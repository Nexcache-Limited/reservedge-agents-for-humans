from __future__ import annotations

from dataclasses import replace
from enum import StrEnum

import pytest
from wp04_helpers import (
    A1_ID,
    A2_ID,
    A3_ID,
    A4_ID,
    ACCEPTANCE_ID,
    BUYER,
    CORRELATION,
    CREATED_AT,
    EXPIRES_AT,
    OCCURRED_AT,
    OFFER_ID,
    OTHER_HASH,
    OWNER,
    PLACEHOLDER_HASH,
    REQUIREMENT_ID,
    RESOURCE_INTENT,
    SUPPLIERS,
)

from itaa_domain.value_objects import (
    ActorRef,
    ActorType,
    AuthorizationAction,
    AuthorizationMode,
    Version,
)
from itaa_policy.approvals import (
    ApprovalDenyReason,
    ApprovalGrant,
    ApprovalKind,
    ApprovalPurpose,
    ApprovalRequest,
    ApprovalResourceType,
    ApprovalStatus,
    validate_approval,
)
from itaa_policy.canonical import (
    SEPARATOR_OFFER_TERMS,
    SEPARATOR_REQUIREMENT_CONFIRMATION,
    SEPARATOR_TRANSACTION_AUTHORIZATION,
    hash_canonical,
)
from itaa_policy.errors import PolicyError


def _a1() -> ApprovalGrant:
    digest = hash_canonical(
        SEPARATOR_REQUIREMENT_CONFIRMATION, {"requirementId": REQUIREMENT_ID.to_primitive()}
    )
    return ApprovalGrant(
        approval_id=A1_ID,
        kind=ApprovalKind.REQUIREMENT_CONFIRMATION,
        purpose=ApprovalPurpose.REQUIREMENT_CONFIRMATION,
        actor=BUYER,
        owner_id=OWNER,
        resource_type=ApprovalResourceType.REQUIREMENT,
        resource_id=REQUIREMENT_ID.to_primitive(),
        resource_version=Version(1),
        payload_hash=digest,
        issued_at=CREATED_AT,
        expires_at=EXPIRES_AT,
        status=ApprovalStatus.ACTIVE,
        correlation_id=CORRELATION,
    )


def _a2(manifest=PLACEHOLDER_HASH, content=OTHER_HASH, count: int = 3) -> ApprovalGrant:
    return ApprovalGrant(
        approval_id=A2_ID,
        kind=ApprovalKind.PURCHASE_INTENT_DISPATCH,
        purpose=ApprovalPurpose.PURCHASE_INTENT_DISPATCH,
        actor=BUYER,
        owner_id=OWNER,
        resource_type=ApprovalResourceType.PURCHASE_INTENT,
        resource_id=RESOURCE_INTENT.to_primitive(),
        resource_version=Version(2),
        payload_hash=manifest,
        issued_at=CREATED_AT,
        expires_at=EXPIRES_AT,
        status=ApprovalStatus.ACTIVE,
        correlation_id=CORRELATION,
        content_hash=content,
        manifest_hash=manifest,
        recipient_count=count,
        solicitation_expires_at=EXPIRES_AT,
    )


def _a3() -> ApprovalGrant:
    terms = hash_canonical(SEPARATOR_OFFER_TERMS, {"totalMinor": 11900, "currency": "USD"})
    return ApprovalGrant(
        approval_id=A3_ID,
        kind=ApprovalKind.OFFER_ACCEPTANCE,
        purpose=ApprovalPurpose.OFFER_ACCEPTANCE,
        actor=BUYER,
        owner_id=OWNER,
        resource_type=ApprovalResourceType.OFFER,
        resource_id=OFFER_ID.to_primitive(),
        resource_version=Version(1),
        payload_hash=terms,
        issued_at=CREATED_AT,
        expires_at=EXPIRES_AT,
        status=ApprovalStatus.ACTIVE,
        correlation_id=CORRELATION,
        intent_id=RESOURCE_INTENT,
        offer_id=OFFER_ID,
        offer_version=Version(1),
        terms_hash=terms,
        offer_valid_until=EXPIRES_AT,
    )


def _a4() -> ApprovalGrant:
    request = {
        "action": "reserve_parking",
        "amountMinor": 11900,
        "currency": "USD",
        "supplierToken": SUPPLIERS[0].to_primitive(),
        "mode": "SIMULATED",
        "acceptanceId": ACCEPTANCE_ID.to_primitive(),
    }
    digest = hash_canonical(SEPARATOR_TRANSACTION_AUTHORIZATION, request)
    return ApprovalGrant(
        approval_id=A4_ID,
        kind=ApprovalKind.TRANSACTION_AUTHORIZATION,
        purpose=ApprovalPurpose.TRANSACTION_AUTHORIZATION,
        actor=BUYER,
        owner_id=OWNER,
        resource_type=ApprovalResourceType.TRANSACTION,
        resource_id=ACCEPTANCE_ID.to_primitive(),
        resource_version=Version(1),
        payload_hash=digest,
        issued_at=CREATED_AT,
        expires_at=EXPIRES_AT,
        status=ApprovalStatus.ACTIVE,
        correlation_id=CORRELATION,
        simulation=True,
        acceptance_id=ACCEPTANCE_ID,
        action=AuthorizationAction.RESERVE_PARKING,
        amount_minor=11900,
        currency="USD",
        supplier_token=SUPPLIERS[0],
        mode=AuthorizationMode.SIMULATED,
        request_hash=digest,
        decision_expires_at=EXPIRES_AT,
    )


def _request_from(grant: ApprovalGrant) -> ApprovalRequest:
    return ApprovalRequest(
        kind=grant.kind,
        purpose=grant.purpose,
        actor=grant.actor,
        owner_id=grant.owner_id,
        resource_type=grant.resource_type,
        resource_id=grant.resource_id,
        resource_version=grant.resource_version,
        payload_hash=grant.payload_hash,
        occurred_at=OCCURRED_AT,
        content_hash=grant.content_hash,
        manifest_hash=grant.manifest_hash,
        recipient_count=grant.recipient_count,
        solicitation_expires_at=grant.solicitation_expires_at,
        intent_id=grant.intent_id,
        offer_id=grant.offer_id,
        offer_version=grant.offer_version,
        terms_hash=grant.terms_hash,
        offer_valid_until=grant.offer_valid_until,
        acceptance_id=grant.acceptance_id,
        action=grant.action,
        amount_minor=grant.amount_minor,
        currency=grant.currency,
        supplier_token=grant.supplier_token,
        mode=grant.mode,
        request_hash=grant.request_hash,
        decision_expires_at=grant.decision_expires_at,
        prior_approval_ids=frozenset({A2_ID, A3_ID})
        if grant.kind is ApprovalKind.TRANSACTION_AUTHORIZATION
        else frozenset(),
    )


def test_matching_a1_a2_a3_a4_allow() -> None:
    for grant in (_a1(), _a2(), _a3(), _a4()):
        decision = validate_approval(grant, _request_from(grant))
        assert decision.allowed is True


def test_kinds_are_not_interchangeable() -> None:
    a2 = _a2()
    a4_request = _request_from(_a4())
    decision = validate_approval(a2, a4_request)
    assert decision.reason is ApprovalDenyReason.KIND_MISMATCH
    a4 = _a4()
    a2_request = _request_from(a2)
    assert validate_approval(a4, a2_request).reason is ApprovalDenyReason.KIND_MISMATCH


def test_wrong_actor_purpose_version_hash_recipient_and_expiry_deny() -> None:
    grant = _a2()
    request = _request_from(grant)
    other_actor = ActorRef(
        ActorType.BUYER, grant.owner_id.__class__("ar_01k2m3n4p5q6r7s8t9v0w1x2k9")
    )
    assert (
        validate_approval(grant, replace(request, actor=other_actor)).reason
        is ApprovalDenyReason.ACTOR_MISMATCH
    )
    assert (
        validate_approval(grant, replace(request, purpose=ApprovalPurpose.OFFER_ACCEPTANCE)).reason
        is ApprovalDenyReason.PURPOSE_MISMATCH
    )
    assert (
        validate_approval(grant, replace(request, resource_version=Version(9))).reason
        is ApprovalDenyReason.VERSION_MISMATCH
    )
    assert (
        validate_approval(
            grant, replace(request, payload_hash=OTHER_HASH, manifest_hash=OTHER_HASH)
        ).reason
        is ApprovalDenyReason.HASH_MISMATCH
    )
    assert (
        validate_approval(grant, replace(request, recipient_count=2)).reason
        is ApprovalDenyReason.RECIPIENT_COUNT_MISMATCH
    )
    assert (
        validate_approval(grant, replace(request, occurred_at=EXPIRES_AT)).reason
        is ApprovalDenyReason.EXPIRED
    )


def test_a3_wrong_offer_version_and_terms_deny() -> None:
    grant = _a3()
    request = _request_from(grant)
    assert (
        validate_approval(grant, replace(request, offer_version=Version(2))).reason
        is ApprovalDenyReason.VERSION_MISMATCH
    )
    assert (
        validate_approval(
            grant, replace(request, terms_hash=OTHER_HASH, payload_hash=OTHER_HASH)
        ).reason
        is ApprovalDenyReason.HASH_MISMATCH
    )


def test_a4_wrong_amount_currency_supplier_action_mode_and_reused_id_deny() -> None:
    grant = _a4()
    request = _request_from(grant)
    assert (
        validate_approval(grant, replace(request, amount_minor=1)).reason
        is ApprovalDenyReason.AMOUNT_MISMATCH
    )
    assert (
        validate_approval(grant, replace(request, currency="EUR")).reason
        is ApprovalDenyReason.CURRENCY_MISMATCH
    )
    assert (
        validate_approval(grant, replace(request, supplier_token=SUPPLIERS[1])).reason
        is ApprovalDenyReason.SUPPLIER_MISMATCH
    )

    class FakeMode(StrEnum):
        LIVE = "LIVE"

    with pytest.raises(PolicyError):
        replace(grant, mode=FakeMode.LIVE)  # type: ignore[arg-type]
    reused = replace(request, prior_approval_ids=frozenset({A4_ID}))
    assert validate_approval(grant, reused).reason is ApprovalDenyReason.APPROVAL_REUSED


def test_raw_kind_string_is_unknown() -> None:
    grant = _a1()
    request = _request_from(grant)
    with pytest.raises(PolicyError, match="invalid_enum"):
        replace(request, kind="REQUIREMENT_CONFIRMATION")  # type: ignore[arg-type]


def test_missing_grant_denies() -> None:
    assert validate_approval(None, _request_from(_a1())).reason is ApprovalDenyReason.MISSING
