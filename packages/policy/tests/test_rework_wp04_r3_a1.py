from __future__ import annotations

from dataclasses import replace

import pytest
from test_envelopes import _recipients
from test_rework_wp04_r1 import _a2_for, _binding
from test_rework_wp04_r3 import (
    INJECTED_IDENTITY,
    REPLACEMENT_BUYER,
    REPLACEMENT_INTENT,
    REPLACEMENT_INVITATION,
    UNLISTED_SUPPLIER,
    _assert_closed,
    _authorize,
    _copy_rows,
    _rehash,
    _replaced_envelope_binding,
    _verify,
)
from wp04_helpers import (
    BUYER,
    CREATED_AT,
    EXPIRES_AT,
    OCCURRED_AT,
    OTHER_HASH,
    OWNER,
    RESOURCE_INTENT,
    SUPPLIERS,
    load_jfk,
)

from itaa_domain.identifiers import BuyerToken, IntentId
from itaa_domain.value_objects import Version
from itaa_policy.disclosure import DisclosurePurpose
from itaa_policy.envelopes import (
    RecipientAssignment,
    authorize_dispatch,
    bind_solicitation,
    verify_dispatch,
)
from itaa_policy.errors import PolicyError
from itaa_policy.isolation import SupplierInvitationToken

FOREIGN_REPLACEMENT_INVITATION = SupplierInvitationToken("iv_01k2m3n4p5q6r7s8t9v0w1x2j8")
FOREIGN_REPLACEMENT_INTENT = IntentId("pi_01k2m3n4p5q6r7s8t9v0w1x2p8")
FOREIGN_REPLACEMENT_BUYER = BuyerToken("bs_01k2m3n4p5q6r7s8t9v0w1x2q8")


def _authorize_as(binding, supplier=SUPPLIERS[0]):
    return authorize_dispatch(
        _a2_for(binding),
        binding=binding,
        supplier_token=supplier,
        occurred_at=OCCURRED_AT,
        actor=BUYER,
        owner_id=OWNER,
    )


def _verify_as(binding, supplier):
    return verify_dispatch(
        binding,
        supplier_token=supplier,
        purpose=DisclosurePurpose.PURCHASE_INTENT_DISPATCH,
        intent_resource_version=Version(2),
        occurred_at=OCCURRED_AT,
    )


def _foreign_row(rows: list[dict[str, str]]) -> dict[str, str]:
    return next(row for row in rows if row["supplierToken"] == SUPPLIERS[1].to_primitive())


def _replaced_foreign_envelope_binding():
    binding = _binding()
    original = _recipients()[1]
    replacement = bind_solicitation(
        load_jfk(),
        intent_resource_id=RESOURCE_INTENT,
        intent_resource_version=Version(2),
        purpose=DisclosurePurpose.PURCHASE_INTENT_DISPATCH,
        expires_at=EXPIRES_AT,
        recipients=(
            RecipientAssignment(
                supplier_token=SUPPLIERS[1],
                invitation=FOREIGN_REPLACEMENT_INVITATION,
                scoped_intent_id=FOREIGN_REPLACEMENT_INTENT,
                scoped_buyer_token=FOREIGN_REPLACEMENT_BUYER,
                valid_from=CREATED_AT,
                valid_until=EXPIRES_AT,
                capabilities=original.capabilities,
            ),
        ),
    )
    envelopes = list(binding.envelopes)
    envelopes[1] = replacement.envelopes[0]
    return replace(binding, envelopes=tuple(envelopes))


def test_foreign_identity_text_in_invitation_fails_while_dispatching_selected() -> None:
    binding = _binding()
    rows = list(_copy_rows(binding))
    _foreign_row(rows)["invitationToken"] = INJECTED_IDENTITY
    tampered = _rehash(binding, tuple(rows))
    with pytest.raises(PolicyError) as captured:
        _verify(tampered)
    assert captured.value.field == "invitation_token"
    assert captured.value.code == "invalid_opaque_syntax"
    _assert_closed(captured.value)
    assert INJECTED_IDENTITY not in str(captured.value)
    with pytest.raises(PolicyError):
        _authorize(tampered)


@pytest.mark.parametrize(
    ("field", "error_field", "code"),
    [
        ("supplierToken", "supplier_token", "invalid_opaque_syntax"),
        ("invitationToken", "invitation_token", "invalid_opaque_syntax"),
        ("scopedIntentId", "scoped_intent_id", "invalid_opaque_syntax"),
        ("scopedBuyerToken", "scoped_buyer_token", "invalid_opaque_syntax"),
        ("envelopeHash", "envelope_hash", "invalid_sha256_shape"),
    ],
)
def test_foreign_invalid_opaque_syntax_fails_closed(
    field: str, error_field: str, code: str
) -> None:
    binding = _binding()
    rows = list(_copy_rows(binding))
    _foreign_row(rows)[field] = INJECTED_IDENTITY
    tampered = _rehash(binding, tuple(rows))
    with pytest.raises(PolicyError) as captured:
        _verify(tampered)
    assert captured.value.field == error_field
    assert captured.value.code == code
    _assert_closed(captured.value)


@pytest.mark.parametrize(
    ("field", "value", "error_field"),
    [
        ("supplierToken", SUPPLIERS[2].to_primitive(), "supplier_token"),
        ("invitationToken", None, "invitation_token"),
        ("scopedIntentId", None, "scoped_intent_id"),
        ("scopedBuyerToken", None, "scoped_buyer_token"),
        ("envelopeHash", None, "envelope_hash"),
    ],
)
def test_duplicate_foreign_bound_values_fail_while_dispatching_selected(
    field: str, value: str | None, error_field: str
) -> None:
    binding = _binding()
    rows = list(_copy_rows(binding))
    donor = next(row for row in rows if row["supplierToken"] == SUPPLIERS[2].to_primitive())
    if value is None:
        value = donor[field]
    _foreign_row(rows)[field] = value
    tampered = _rehash(binding, tuple(rows))
    with pytest.raises(PolicyError) as captured:
        _verify(tampered)
    assert captured.value.field == error_field
    assert captured.value.code == "duplicate"
    _assert_closed(captured.value)


def test_appended_duplicate_foreign_row_fails_while_dispatching_selected() -> None:
    binding = _binding()
    rows = _copy_rows(binding)
    tampered = _rehash(binding, (*rows, dict(_foreign_row(list(rows)))))
    with pytest.raises(PolicyError) as captured:
        _verify(tampered)
    assert captured.value.field == "recipient_count"
    assert captured.value.code == "mismatch"
    _assert_closed(captured.value)


def test_extra_foreign_row_fails_when_selected_row_is_exact() -> None:
    binding = _binding()
    rows = _copy_rows(binding)
    extra = dict(_foreign_row(list(rows)))
    extra["supplierToken"] = UNLISTED_SUPPLIER.to_primitive()
    extra["invitationToken"] = REPLACEMENT_INVITATION.to_primitive()
    extra["scopedIntentId"] = REPLACEMENT_INTENT.to_primitive()
    extra["scopedBuyerToken"] = REPLACEMENT_BUYER.to_primitive()
    extra["envelopeHash"] = OTHER_HASH.to_primitive()
    tampered = _rehash(binding, (*rows, extra))
    with pytest.raises(PolicyError) as captured:
        _verify(tampered)
    assert captured.value.field == "recipient_count"
    assert captured.value.code == "mismatch"
    _assert_closed(captured.value)


def test_missing_foreign_row_fails_when_selected_row_is_exact() -> None:
    binding = _binding()
    rows = tuple(
        row for row in _copy_rows(binding) if row["supplierToken"] != SUPPLIERS[1].to_primitive()
    )
    tampered = _rehash(binding, rows)
    with pytest.raises(PolicyError) as captured:
        _verify(tampered)
    assert captured.value.field == "recipient_count"
    assert captured.value.code == "mismatch"
    _assert_closed(captured.value)


def test_replacing_non_selected_envelope_fails_while_dispatching_selected() -> None:
    binding = _replaced_foreign_envelope_binding()
    with pytest.raises(PolicyError) as captured:
        _verify(binding)
    assert captured.value.code == "mismatch"
    _assert_closed(captured.value)
    with pytest.raises(PolicyError):
        _authorize(binding)


def test_reordered_identical_recipient_set_still_verifies() -> None:
    binding = _binding()
    reordered = _rehash(binding, tuple(reversed(_copy_rows(binding))))
    verified = _verify(reordered)
    authorized = _authorize(reordered)
    assert verified.assignment.supplier_token == SUPPLIERS[0]
    assert authorized.allowed is True
    assert authorized.envelope is not None
    assert authorized.envelope.envelope_hash == verified.envelope_hash


def test_original_three_envelope_manifest_authorizes_each_listed_supplier() -> None:
    binding = _binding()
    for supplier in SUPPLIERS:
        verified = _verify_as(binding, supplier)
        authorized = _authorize_as(binding, supplier)
        assert authorized.allowed is True
        assert authorized.envelope is not None
        assert verified.assignment.supplier_token == supplier
        assert authorized.envelope.assignment.supplier_token == supplier


def test_original_replacement_envelope_regression_remains_closed() -> None:
    binding = _replaced_envelope_binding()
    with pytest.raises(PolicyError) as captured:
        _verify(binding)
    assert captured.value.code == "mismatch"
    _assert_closed(captured.value)
