from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

import pytest
from test_envelopes import _recipients
from test_rework_wp04_r1 import _a2_for, _binding
from wp04_helpers import (
    BUYER,
    CREATED_AT,
    EXPIRES_AT,
    INVITATIONS,
    OCCURRED_AT,
    OTHER_HASH,
    OWNER,
    RESOURCE_INTENT,
    SCOPED_BUYERS,
    SCOPED_INTENTS,
    SUPPLIERS,
    load_jfk,
)

from itaa_domain.identifiers import BuyerToken, IntentId, SupplierToken
from itaa_domain.value_objects import Version
from itaa_policy.canonical import SEPARATOR_DISCLOSURE_MANIFEST, hash_canonical
from itaa_policy.disclosure import DisclosurePurpose
from itaa_policy.envelopes import (
    RecipientAssignment,
    authorize_dispatch,
    bind_solicitation,
    verify_dispatch,
)
from itaa_policy.errors import PolicyError
from itaa_policy.isolation import SupplierInvitationToken

REPLACEMENT_INVITATION = SupplierInvitationToken("iv_01k2m3n4p5q6r7s8t9v0w1x2j9")
REPLACEMENT_INTENT = IntentId("pi_01k2m3n4p5q6r7s8t9v0w1x2p9")
REPLACEMENT_BUYER = BuyerToken("bs_01k2m3n4p5q6r7s8t9v0w1x2q9")
UNLISTED_SUPPLIER = SupplierToken("sp_01k2m3n4p5q6r7s8t9v0w1x2b9")
INJECTED_IDENTITY = "alice@example.com"


def _opaque_values() -> tuple[str, ...]:
    return (
        SUPPLIERS[0].to_primitive(),
        SUPPLIERS[1].to_primitive(),
        INVITATIONS[0].to_primitive(),
        REPLACEMENT_INVITATION.to_primitive(),
        SCOPED_INTENTS[0].to_primitive(),
        REPLACEMENT_INTENT.to_primitive(),
        SCOPED_BUYERS[0].to_primitive(),
        REPLACEMENT_BUYER.to_primitive(),
        OTHER_HASH.to_primitive(),
        UNLISTED_SUPPLIER.to_primitive(),
        INJECTED_IDENTITY,
    )


def _assert_closed(error: PolicyError) -> None:
    text = str(error)
    for value in _opaque_values():
        assert value not in text


def _verify(binding):
    return verify_dispatch(
        binding,
        supplier_token=SUPPLIERS[0],
        purpose=DisclosurePurpose.PURCHASE_INTENT_DISPATCH,
        intent_resource_version=Version(2),
        occurred_at=OCCURRED_AT,
    )


def _authorize(binding):
    return authorize_dispatch(
        _a2_for(binding),
        binding=binding,
        supplier_token=SUPPLIERS[0],
        occurred_at=OCCURRED_AT,
        actor=BUYER,
        owner_id=OWNER,
    )


def _copy_rows(binding) -> tuple[dict[str, str], ...]:
    return tuple(dict(row) for row in binding.manifest.recipients)


def _rehash(binding, recipients: Sequence[object]):
    material = {
        "contentHash": binding.manifest.content_hash.to_primitive(),
        "intentResourceId": binding.manifest.intent_resource_id.to_primitive(),
        "intentResourceVersion": binding.manifest.intent_resource_version.to_primitive(),
        "purpose": binding.manifest.purpose.value,
        "expiresAt": binding.manifest.expires_at,
        "recipients": list(recipients),
    }
    digest = hash_canonical(SEPARATOR_DISCLOSURE_MANIFEST, material)
    return replace(
        binding,
        preview=replace(binding.preview, manifest_hash=digest),
        manifest=replace(binding.manifest, recipients=tuple(recipients), manifest_hash=digest),
    )


def _replaced_envelope_binding():
    binding = _binding()
    original = _recipients()[0]
    replacement = bind_solicitation(
        load_jfk(),
        intent_resource_id=RESOURCE_INTENT,
        intent_resource_version=Version(2),
        purpose=DisclosurePurpose.PURCHASE_INTENT_DISPATCH,
        expires_at=EXPIRES_AT,
        recipients=(
            RecipientAssignment(
                supplier_token=SUPPLIERS[0],
                invitation=REPLACEMENT_INVITATION,
                scoped_intent_id=REPLACEMENT_INTENT,
                scoped_buyer_token=REPLACEMENT_BUYER,
                valid_from=CREATED_AT,
                valid_until=EXPIRES_AT,
                capabilities=original.capabilities,
            ),
        ),
    )
    replaced = replacement.envelopes[0]
    assert replaced.envelope_hash != binding.envelopes[0].envelope_hash
    assert replaced.assignment.invitation != binding.envelopes[0].assignment.invitation
    return replace(binding, envelopes=(replaced, *binding.envelopes[1:]))


def test_replacement_envelope_cannot_verify_or_authorize_against_approved_row() -> None:
    binding = _replaced_envelope_binding()
    approved = next(
        row
        for row in binding.manifest.recipients
        if row["supplierToken"] == SUPPLIERS[0].to_primitive()
    )
    with pytest.raises(PolicyError) as verified:
        _verify(binding)
    with pytest.raises(PolicyError) as authorized:
        _authorize(binding)
    for captured in (verified, authorized):
        assert captured.value.field in {
            "invitation_token",
            "scoped_intent_id",
            "scoped_buyer_token",
            "envelope_hash",
        }
        assert captured.value.code == "mismatch"
        _assert_closed(captured.value)
    assert approved["envelopeHash"] != binding.envelopes[0].envelope_hash.to_primitive()
    assert approved["invitationToken"] != binding.envelopes[0].assignment.invitation.to_primitive()


@pytest.mark.parametrize(
    ("field", "value", "error_field", "code"),
    [
        ("supplierToken", UNLISTED_SUPPLIER.to_primitive(), "recipient_row", "missing"),
        ("invitationToken", REPLACEMENT_INVITATION.to_primitive(), "invitation_token", "mismatch"),
        ("scopedIntentId", REPLACEMENT_INTENT.to_primitive(), "scoped_intent_id", "mismatch"),
        ("scopedBuyerToken", REPLACEMENT_BUYER.to_primitive(), "scoped_buyer_token", "mismatch"),
        ("envelopeHash", OTHER_HASH.to_primitive(), "envelope_hash", "mismatch"),
    ],
)
def test_each_recipient_row_field_mismatch_fails(
    field: str, value: str, error_field: str, code: str
) -> None:
    binding = _binding()
    rows = list(_copy_rows(binding))
    target = next(row for row in rows if row["supplierToken"] == SUPPLIERS[0].to_primitive())
    target[field] = value
    tampered = _rehash(binding, tuple(rows))
    with pytest.raises(PolicyError) as captured:
        _verify(tampered)
    assert captured.value.field == error_field
    assert captured.value.code == code
    _assert_closed(captured.value)
    with pytest.raises(PolicyError):
        _authorize(tampered)


def test_missing_recipient_row_fails() -> None:
    binding = _binding()
    rows = tuple(
        row for row in _copy_rows(binding) if row["supplierToken"] != SUPPLIERS[0].to_primitive()
    )
    tampered = _rehash(binding, rows)
    with pytest.raises(PolicyError) as captured:
        _verify(tampered)
    assert captured.value.field == "recipient_count"
    assert captured.value.code == "mismatch"
    _assert_closed(captured.value)


def test_duplicate_recipient_row_fails_even_if_one_matches() -> None:
    binding = _binding()
    rows = _copy_rows(binding)
    matched = next(row for row in rows if row["supplierToken"] == SUPPLIERS[0].to_primitive())
    tampered = _rehash(binding, (*rows, dict(matched)))
    with pytest.raises(PolicyError) as captured:
        _verify(tampered)
    assert captured.value.field == "recipient_count"
    assert captured.value.code == "mismatch"
    _assert_closed(captured.value)


@pytest.mark.parametrize(
    ("mutator", "code"),
    [
        (lambda row: ["not-a-row"], "invalid_shape"),
        (lambda row: None, "invalid_shape"),
        (
            lambda row: {key: value for key, value in row.items() if key != "invitationToken"},
            "invalid_shape",
        ),
        (lambda row: {**row, "envelopeHash": 1}, "invalid_shape"),
        (lambda row: {**row, INJECTED_IDENTITY: "injected"}, "unknown_field"),
    ],
)
def test_malformed_or_unknown_recipient_row_fails(mutator, code: str) -> None:
    binding = _binding()
    rows = list(_copy_rows(binding))
    index = next(
        i for i, row in enumerate(rows) if row["supplierToken"] == SUPPLIERS[0].to_primitive()
    )
    rows[index] = mutator(rows[index])
    tampered = _rehash(binding, tuple(rows))
    with pytest.raises(PolicyError) as captured:
        _verify(tampered)
    assert captured.value.field == "recipient_row"
    assert captured.value.code == code
    _assert_closed(captured.value)


def test_malformed_foreign_row_fails_closed() -> None:
    binding = _binding()
    rows = list(_copy_rows(binding))
    index = next(
        i for i, row in enumerate(rows) if row["supplierToken"] == SUPPLIERS[1].to_primitive()
    )
    rows[index] = {**rows[index], "competitor": INJECTED_IDENTITY}
    tampered = _rehash(binding, tuple(rows))
    with pytest.raises(PolicyError) as captured:
        _verify(tampered)
    assert captured.value.field == "recipient_row"
    assert captured.value.code == "unknown_field"
    _assert_closed(captured.value)


def test_original_listed_envelope_still_authorizes_and_matches_row() -> None:
    binding = _binding()
    verified = _verify(binding)
    authorized = _authorize(binding)
    assert authorized.allowed is True
    assert authorized.envelope is not None
    assert verified.envelope_hash == authorized.envelope.envelope_hash
    row = next(
        item
        for item in binding.manifest.recipients
        if item["supplierToken"] == SUPPLIERS[0].to_primitive()
    )
    envelope = authorized.envelope
    assert row["supplierToken"] == envelope.assignment.supplier_token.to_primitive()
    assert row["invitationToken"] == envelope.assignment.invitation.to_primitive()
    assert row["scopedIntentId"] == envelope.assignment.scoped_intent_id.to_primitive()
    assert row["scopedBuyerToken"] == envelope.assignment.scoped_buyer_token.to_primitive()
    assert row["envelopeHash"] == envelope.envelope_hash.to_primitive()
