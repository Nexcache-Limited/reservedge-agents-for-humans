from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from test_approvals import _a1, _a2, _a3, _a4, _request_from
from test_envelopes import _recipients
from wp04_helpers import (
    A2_ID,
    BUYER,
    CORRELATION,
    CREATED_AT,
    EXPIRES_AT,
    OCCURRED_AT,
    OWNER,
    RESOURCE_INTENT,
    SUPPLIERS,
    clone,
    load_jfk,
)

from itaa_domain.value_objects import JS_SAFE_MAX, Version, parse_utc
from itaa_policy.approvals import (
    ApprovalDenyReason,
    ApprovalGrant,
    ApprovalKind,
    ApprovalPurpose,
    ApprovalResourceType,
    ApprovalStatus,
)
from itaa_policy.canonical import content_hash_material
from itaa_policy.disclosure import DisclosurePurpose, inspect_parking_v1
from itaa_policy.envelopes import (
    RecipientAssignment,
    authorize_dispatch,
    bind_solicitation,
    verify_dispatch,
)
from itaa_policy.errors import PolicyError
from itaa_policy.idempotency import ResultRef
from itaa_policy.isolation import SupplierCapability, authorize_supplier


def _binding():
    return bind_solicitation(
        load_jfk(),
        intent_resource_id=RESOURCE_INTENT,
        intent_resource_version=Version(2),
        purpose=DisclosurePurpose.PURCHASE_INTENT_DISPATCH,
        expires_at=EXPIRES_AT,
        recipients=_recipients(),
    )


def _a2_for(binding) -> ApprovalGrant:
    return ApprovalGrant(
        approval_id=A2_ID,
        kind=ApprovalKind.PURCHASE_INTENT_DISPATCH,
        purpose=ApprovalPurpose.PURCHASE_INTENT_DISPATCH,
        actor=BUYER,
        owner_id=OWNER,
        resource_type=ApprovalResourceType.PURCHASE_INTENT,
        resource_id=binding.manifest.intent_resource_id.to_primitive(),
        resource_version=binding.manifest.intent_resource_version,
        payload_hash=binding.manifest.manifest_hash,
        issued_at=CREATED_AT,
        expires_at=EXPIRES_AT,
        status=ApprovalStatus.ACTIVE,
        correlation_id=CORRELATION,
        content_hash=binding.manifest.content_hash,
        manifest_hash=binding.manifest.manifest_hash,
        recipient_count=len(binding.envelopes),
        solicitation_expires_at=parse_utc(binding.manifest.expires_at, "expires_at"),
    )


def test_verify_dispatch_is_not_authorization() -> None:
    binding = _binding()
    envelope = verify_dispatch(
        binding,
        supplier_token=SUPPLIERS[0],
        purpose=DisclosurePurpose.PURCHASE_INTENT_DISPATCH,
        intent_resource_version=Version(2),
        occurred_at=OCCURRED_AT,
    )
    denied = authorize_dispatch(
        None,
        binding=binding,
        supplier_token=SUPPLIERS[0],
        occurred_at=OCCURRED_AT,
        actor=BUYER,
        owner_id=OWNER,
    )
    assert envelope.envelope_hash == binding.envelopes[0].envelope_hash
    assert denied.allowed is False
    assert denied.envelope is None
    assert denied.decision.reason is ApprovalDenyReason.MISSING


@pytest.mark.parametrize(
    ("grant_factory", "reason"),
    [
        (lambda binding: None, ApprovalDenyReason.MISSING),
        (lambda binding: _a1(), ApprovalDenyReason.KIND_MISMATCH),
        (lambda binding: _a3(), ApprovalDenyReason.KIND_MISMATCH),
        (lambda binding: _a4(), ApprovalDenyReason.KIND_MISMATCH),
        (
            lambda binding: replace(_a2_for(binding), resource_version=Version(9)),
            ApprovalDenyReason.VERSION_MISMATCH,
        ),
        (
            lambda binding: replace(_a2_for(binding), recipient_count=2),
            ApprovalDenyReason.RECIPIENT_COUNT_MISMATCH,
        ),
        (
            lambda binding: replace(_a2_for(binding), purpose=ApprovalPurpose.OFFER_ACCEPTANCE),
            ApprovalDenyReason.PURPOSE_MISMATCH,
        ),
    ],
)
def test_authorize_dispatch_denies_without_fresh_exact_a2(grant_factory, reason) -> None:
    binding = _binding()
    if reason is ApprovalDenyReason.PURPOSE_MISMATCH:
        with pytest.raises(PolicyError, match="kind_mismatch"):
            grant_factory(binding)
        return
    grant = grant_factory(binding)
    decision = authorize_dispatch(
        grant,
        binding=binding,
        supplier_token=SUPPLIERS[0],
        occurred_at=OCCURRED_AT,
        actor=BUYER,
        owner_id=OWNER,
    )
    assert decision.allowed is False
    assert decision.envelope is None
    assert decision.decision.reason is reason


def test_authorize_dispatch_denies_expired_and_changed_bindings() -> None:
    binding = _binding()
    grant = _a2_for(binding)
    expired = authorize_dispatch(
        grant,
        binding=binding,
        supplier_token=SUPPLIERS[0],
        occurred_at=EXPIRES_AT,
        actor=BUYER,
        owner_id=OWNER,
    )
    assert expired.allowed is False
    assert expired.decision.reason is ApprovalDenyReason.EXPIRED
    mutated = load_jfk()
    mutated["requirements"]["shuttleMaxMinutes"] = 30
    changed = bind_solicitation(
        mutated,
        intent_resource_id=RESOURCE_INTENT,
        intent_resource_version=Version(2),
        purpose=DisclosurePurpose.PURCHASE_INTENT_DISPATCH,
        expires_at=EXPIRES_AT,
        recipients=_recipients(),
    )
    stale = authorize_dispatch(
        grant,
        binding=changed,
        supplier_token=SUPPLIERS[0],
        occurred_at=OCCURRED_AT,
        actor=BUYER,
        owner_id=OWNER,
    )
    assert stale.allowed is False
    assert stale.envelope is None
    assert stale.decision.reason is ApprovalDenyReason.HASH_MISMATCH


def test_authorize_dispatch_rejects_unlisted_and_cross_supplier() -> None:
    binding = _binding()
    grant = _a2_for(binding)
    authorized = authorize_dispatch(
        grant,
        binding=binding,
        supplier_token=SUPPLIERS[0],
        occurred_at=OCCURRED_AT,
        actor=BUYER,
        owner_id=OWNER,
    )
    assert authorized.allowed is True
    assert authorized.envelope is not None
    assert authorized.envelope.assignment.supplier_token == SUPPLIERS[0]
    with pytest.raises(PolicyError, match="not_in_manifest"):
        authorize_dispatch(
            grant,
            binding=binding,
            supplier_token=SUPPLIERS[0].__class__("sp_01k2m3n4p5q6r7s8t9v0w1x2b9"),
            occurred_at=OCCURRED_AT,
            actor=BUYER,
            owner_id=OWNER,
        )
    foreign = authorize_supplier(
        granted=authorized.envelope.scope,
        principal=binding.envelopes[1].scope.principal,
        invitation=authorized.envelope.assignment.invitation,
        intent_id=authorized.envelope.assignment.scoped_intent_id,
        capability=SupplierCapability.INVITATION_READ,
        occurred_at=OCCURRED_AT,
    )
    assert foreign.allowed is False


def test_a4_negative_amount_and_lowercase_currency_cannot_be_constructed() -> None:
    grant = _a4()
    with pytest.raises(PolicyError) as captured_grant:
        replace(grant, amount_minor=-1, currency="usd")
    with pytest.raises(PolicyError) as captured_request:
        replace(_request_from(grant), amount_minor=-1, currency="usd")
    for captured in (captured_grant, captured_request):
        text = str(captured.value)
        assert "usd" not in text
        assert "-1" not in text
        assert captured.value.field in {"amount_minor", "currency"}


@pytest.mark.parametrize(
    ("amount", "currency"),
    [
        (-1, "USD"),
        (JS_SAFE_MAX + 1, "USD"),
        (1.5, "USD"),
        (True, "USD"),
        (11900, "usd"),
        (11900, "US"),
        (11900, "USDT"),
        (11900, "US1"),
    ],
)
def test_malformed_a4_money_is_rejected(amount: object, currency: object) -> None:
    grant = _a4()
    with pytest.raises(PolicyError) as captured:
        replace(grant, amount_minor=amount, currency=currency)  # type: ignore[arg-type]
    assert "alice" not in str(captured.value)
    assert "@" not in str(captured.value)


def test_malformed_ids_hashes_and_deadlines_fail_closed() -> None:
    grant = _a4()
    with pytest.raises(PolicyError, match="invalid_opaque_syntax") as captured:
        replace(grant, resource_id="alice@example.com")
    assert "alice@example.com" not in str(captured.value)
    with pytest.raises(PolicyError, match="invalid_type"):
        replace(grant, payload_hash="sha256:" + ("a" * 64))  # type: ignore[arg-type]
    with pytest.raises(PolicyError, match="incoherent_window"):
        replace(_a2(), solicitation_expires_at=CREATED_AT)
    with pytest.raises(PolicyError, match="incoherent_window"):
        replace(_a2(), solicitation_expires_at=EXPIRES_AT + timedelta(days=1))
    with pytest.raises(PolicyError, match="must_equal_acceptance"):
        replace(grant, resource_id="ac_01k2m3n4p5q6r7s8t9v0w1x2d9")


def test_content_hash_material_rejects_nested_non_string_keys() -> None:
    with pytest.raises(PolicyError, match="non_string_key") as captured:
        content_hash_material({"outer": {1: {"inner": "x"}}})
    assert "1" not in str(captured.value) or captured.value.code == "non_string_key"
    assert captured.value.field == "payload"


def test_supplied_expiry_must_match_payload_and_binds_hashes() -> None:
    source = load_jfk()
    later = datetime(2026, 8, 23, 15, 0, tzinfo=UTC)
    with pytest.raises(PolicyError, match="expires_at") as captured:
        inspect_parking_v1(
            source,
            intent_resource_id=RESOURCE_INTENT,
            intent_resource_version=Version(1),
            purpose=DisclosurePurpose.PURCHASE_INTENT_DISPATCH,
            expires_at=later,
        )
    assert captured.value.code == "mismatch"
    original = inspect_parking_v1(
        source,
        intent_resource_id=RESOURCE_INTENT,
        intent_resource_version=Version(1),
        purpose=DisclosurePurpose.PURCHASE_INTENT_DISPATCH,
        expires_at=EXPIRES_AT,
    )
    changed_source = clone(source)
    changed_source["expiresAt"] = "2026-08-23T15:00:00Z"
    changed = inspect_parking_v1(
        changed_source,
        intent_resource_id=RESOURCE_INTENT,
        intent_resource_version=Version(1),
        purpose=DisclosurePurpose.PURCHASE_INTENT_DISPATCH,
        expires_at=later,
    )
    assert changed[1].content_hash != original[1].content_hash
    assert changed[1].expires_at == "2026-08-23T15:00:00Z"


def test_expiry_change_invalidates_dispatch_authorization() -> None:
    original = _binding()
    grant = _a2_for(original)
    later = datetime(2026, 8, 23, 15, 0, tzinfo=UTC)
    mutated = load_jfk()
    mutated["expiresAt"] = "2026-08-23T15:00:00Z"
    recipients = tuple(
        RecipientAssignment(
            supplier_token=item.supplier_token,
            invitation=item.invitation,
            scoped_intent_id=item.scoped_intent_id,
            scoped_buyer_token=item.scoped_buyer_token,
            valid_from=item.valid_from,
            valid_until=later,
            capabilities=item.capabilities,
        )
        for item in _recipients()
    )
    changed = bind_solicitation(
        mutated,
        intent_resource_id=RESOURCE_INTENT,
        intent_resource_version=Version(2),
        purpose=DisclosurePurpose.PURCHASE_INTENT_DISPATCH,
        expires_at=later,
        recipients=recipients,
    )
    assert changed.manifest.manifest_hash != original.manifest.manifest_hash
    denied = authorize_dispatch(
        grant,
        binding=changed,
        supplier_token=SUPPLIERS[0],
        occurred_at=OCCURRED_AT,
        actor=BUYER,
        owner_id=OWNER,
    )
    assert denied.allowed is False
    assert denied.envelope is None


def test_result_ref_rejects_identity_text() -> None:
    with pytest.raises(PolicyError, match="invalid_opaque_syntax") as captured:
        ResultRef("rr_alice@example.com")
    assert "alice@example.com" not in str(captured.value)
    assert ResultRef("rr_01k2m3n4p5q6r7s8t9v0w1x2r1").to_primitive().startswith("rr_")
