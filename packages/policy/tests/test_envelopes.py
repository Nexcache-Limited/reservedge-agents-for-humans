from __future__ import annotations

import json

import pytest
from wp04_helpers import (
    CREATED_AT,
    EXPIRES_AT,
    INVITATIONS,
    OCCURRED_AT,
    READ_OFFER,
    READ_WRITE,
    RESOURCE_INTENT,
    SCOPED_BUYERS,
    SCOPED_INTENTS,
    SUPPLIERS,
    clone,
    load_jfk,
)

from itaa_domain.identifiers import IntentId, SupplierToken
from itaa_domain.value_objects import Version
from itaa_policy.disclosure import DisclosurePurpose
from itaa_policy.envelopes import RecipientAssignment, bind_solicitation, verify_dispatch
from itaa_policy.errors import PolicyError
from itaa_policy.isolation import SupplierCapability, authorize_supplier


def _recipients() -> tuple[RecipientAssignment, ...]:
    return tuple(
        RecipientAssignment(
            supplier_token=SUPPLIERS[index],
            invitation=INVITATIONS[index],
            scoped_intent_id=SCOPED_INTENTS[index],
            scoped_buyer_token=SCOPED_BUYERS[index],
            valid_from=CREATED_AT,
            valid_until=EXPIRES_AT,
            capabilities=READ_WRITE if index == 0 else READ_OFFER,
        )
        for index in range(3)
    )


def test_three_suppliers_receive_unique_aliases_and_hashes() -> None:
    source = load_jfk()
    original = clone(source)
    binding = bind_solicitation(
        source,
        intent_resource_id=RESOURCE_INTENT,
        intent_resource_version=Version(2),
        purpose=DisclosurePurpose.PURCHASE_INTENT_DISPATCH,
        expires_at=EXPIRES_AT,
        recipients=_recipients(),
    )
    assert source == original
    assert binding.preview.recipient_count == 3
    assert binding.preview.manifest_hash == binding.manifest.manifest_hash
    intents = [item.assignment.scoped_intent_id for item in binding.envelopes]
    buyers = [item.assignment.scoped_buyer_token for item in binding.envelopes]
    invitations = [item.assignment.invitation for item in binding.envelopes]
    hashes = [item.envelope_hash for item in binding.envelopes]
    assert len(set(intents)) == 3
    assert len(set(buyers)) == 3
    assert len(set(invitations)) == 3
    assert len(set(hashes)) == 3
    contents = []
    for envelope in binding.envelopes:
        payload = envelope.payload_dict()
        assert payload["intentId"] == envelope.assignment.scoped_intent_id.to_primitive()
        assert payload["buyerToken"] == envelope.assignment.scoped_buyer_token.to_primitive()
        assert payload["disclosure"]["approvedPayloadHash"] == envelope.content_hash.to_primitive()
        dumped = json.dumps(payload)
        assert "recipientCount" not in dumped
        assert "competitor" not in dumped
        for other in binding.envelopes:
            if other is envelope:
                continue
            assert other.assignment.supplier_token.to_primitive() not in dumped
            assert other.envelope_hash.to_primitive() not in dumped
        contents.append({k: v for k, v in payload.items() if k not in {"intentId", "buyerToken"}})
    assert contents[0] == contents[1] == contents[2]
    verified = verify_dispatch(
        binding,
        supplier_token=SUPPLIERS[0],
        purpose=DisclosurePurpose.PURCHASE_INTENT_DISPATCH,
        intent_resource_version=Version(2),
        occurred_at=OCCURRED_AT,
    )
    assert verified.envelope_hash == binding.envelopes[0].envelope_hash


def test_content_alias_count_and_expiry_changes_invalidate_dispatch() -> None:
    binding = bind_solicitation(
        load_jfk(),
        intent_resource_id=RESOURCE_INTENT,
        intent_resource_version=Version(2),
        purpose=DisclosurePurpose.PURCHASE_INTENT_DISPATCH,
        expires_at=EXPIRES_AT,
        recipients=_recipients(),
    )
    with pytest.raises(PolicyError, match="intent_resource_version"):
        verify_dispatch(
            binding,
            supplier_token=SUPPLIERS[0],
            purpose=DisclosurePurpose.PURCHASE_INTENT_DISPATCH,
            intent_resource_version=Version(3),
            occurred_at=OCCURRED_AT,
        )
    with pytest.raises(PolicyError, match="supplier_token"):
        verify_dispatch(
            binding,
            supplier_token=SupplierToken("sp_01k2m3n4p5q6r7s8t9v0w1x2b9"),
            purpose=DisclosurePurpose.PURCHASE_INTENT_DISPATCH,
            intent_resource_version=Version(2),
            occurred_at=OCCURRED_AT,
        )
    with pytest.raises(PolicyError, match="expired"):
        verify_dispatch(
            binding,
            supplier_token=SUPPLIERS[0],
            purpose=DisclosurePurpose.PURCHASE_INTENT_DISPATCH,
            intent_resource_version=Version(2),
            occurred_at=EXPIRES_AT,
        )
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
    assert changed.manifest.manifest_hash != binding.manifest.manifest_hash
    assert changed.manifest.content_hash != binding.manifest.content_hash


def test_cross_supplier_token_on_foreign_envelope_is_denied() -> None:
    binding = bind_solicitation(
        load_jfk(),
        intent_resource_id=RESOURCE_INTENT,
        intent_resource_version=Version(2),
        purpose=DisclosurePurpose.PURCHASE_INTENT_DISPATCH,
        expires_at=EXPIRES_AT,
        recipients=_recipients(),
    )
    foreign = binding.envelopes[0]
    decision = authorize_supplier(
        granted=binding.envelopes[1].scope,
        principal=foreign.scope.principal,
        invitation=foreign.assignment.invitation,
        intent_id=foreign.assignment.scoped_intent_id,
        capability=SupplierCapability.INVITATION_READ,
        occurred_at=OCCURRED_AT,
    )
    assert decision.allowed is False


def test_duplicate_alias_is_rejected() -> None:
    recipients = list(_recipients())
    recipients[2] = RecipientAssignment(
        supplier_token=SUPPLIERS[2],
        invitation=INVITATIONS[2],
        scoped_intent_id=SCOPED_INTENTS[0],
        scoped_buyer_token=SCOPED_BUYERS[2],
        valid_from=CREATED_AT,
        valid_until=EXPIRES_AT,
        capabilities=READ_OFFER,
    )
    with pytest.raises(PolicyError, match="duplicate"):
        bind_solicitation(
            load_jfk(),
            intent_resource_id=RESOURCE_INTENT,
            intent_resource_version=Version(1),
            purpose=DisclosurePurpose.PURCHASE_INTENT_DISPATCH,
            expires_at=EXPIRES_AT,
            recipients=recipients,
        )


def test_scoped_intent_is_not_the_internal_resource_id() -> None:
    binding = bind_solicitation(
        load_jfk(),
        intent_resource_id=RESOURCE_INTENT,
        intent_resource_version=Version(1),
        purpose=DisclosurePurpose.PURCHASE_INTENT_DISPATCH,
        expires_at=EXPIRES_AT,
        recipients=_recipients(),
    )
    for envelope in binding.envelopes:
        assert envelope.payload["intentId"] != RESOURCE_INTENT.to_primitive()
        assert IntentId(str(envelope.payload["intentId"]))
