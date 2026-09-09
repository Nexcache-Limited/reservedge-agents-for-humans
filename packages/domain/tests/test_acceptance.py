from __future__ import annotations

import pytest
from helpers import (
    ACCEPTANCE_CREATED_AT,
    ACCEPTANCE_ID,
    INTENT_ID,
    OFFER_ID,
    TERMS_HASH,
    USER_APPROVAL_ID,
    make_acceptance,
)

from itaa_domain.acceptance import Acceptance
from itaa_domain.errors import DomainInvariantError
from itaa_domain.value_objects import AcceptanceStatus, Version


def test_acceptance_binds_exact_offer_version_and_hash() -> None:
    acceptance = make_acceptance()
    snapshot = acceptance.to_primitive()
    assert snapshot["offerId"] == OFFER_ID.to_primitive()
    assert snapshot["offerVersion"] == 1
    assert snapshot["acceptedTermsHash"] == TERMS_HASH.to_primitive()
    assert snapshot["buyerApprovalId"] == USER_APPROVAL_ID.to_primitive()
    assert snapshot["status"] == "recorded"
    assert acceptance.is_expired_at(acceptance.expires_at)


def test_acceptance_rejects_expired_at_creation_and_unsupported_status() -> None:
    with pytest.raises(DomainInvariantError):
        Acceptance.record(
            acceptance_id=ACCEPTANCE_ID,
            intent_id=INTENT_ID,
            offer_id=OFFER_ID,
            offer_version=Version.initial(),
            accepted_terms_hash=TERMS_HASH,
            buyer_approval_id=USER_APPROVAL_ID,
            created_at=ACCEPTANCE_CREATED_AT,
            expires_at=ACCEPTANCE_CREATED_AT,
        )
    with pytest.raises(ValueError):
        AcceptanceStatus("expired")
    with pytest.raises(ValueError):
        AcceptanceStatus("superseded")
