from __future__ import annotations

import pytest
from fakes import InMemoryApprovalRepository
from test_rework_wp04_r1 import _a2_for, _binding
from test_rework_wp04_r3 import INJECTED_IDENTITY, _copy_rows, _rehash
from wp04_helpers import A2_ID, BUYER, OCCURRED_AT, OWNER, SUPPLIERS

from itaa_application.dispatch_service import DispatchService
from itaa_policy.errors import PolicyError


def _authorize(binding):
    repo = InMemoryApprovalRepository()
    repo.append(_a2_for(binding))
    return DispatchService(repo).authorize(
        A2_ID,
        binding=binding,
        supplier_token=SUPPLIERS[0],
        occurred_at=OCCURRED_AT,
        actor=BUYER,
        owner_id=OWNER,
    )


def test_dispatch_service_rejects_foreign_invalid_and_duplicate_rows() -> None:
    original = _binding()
    identity_rows = list(_copy_rows(original))
    next(row for row in identity_rows if row["supplierToken"] == SUPPLIERS[1].to_primitive())[
        "invitationToken"
    ] = INJECTED_IDENTITY
    with pytest.raises(PolicyError) as identity:
        _authorize(_rehash(original, tuple(identity_rows)))
    assert identity.value.code == "invalid_opaque_syntax"
    assert INJECTED_IDENTITY not in str(identity.value)

    duplicate_rows = _copy_rows(original)
    foreign = next(
        row for row in duplicate_rows if row["supplierToken"] == SUPPLIERS[1].to_primitive()
    )
    with pytest.raises(PolicyError) as duplicate:
        _authorize(_rehash(original, (*duplicate_rows, dict(foreign))))
    assert duplicate.value.field == "recipient_count"
    assert "sp_" not in str(duplicate.value)
    assert "alice@" not in str(duplicate.value)
