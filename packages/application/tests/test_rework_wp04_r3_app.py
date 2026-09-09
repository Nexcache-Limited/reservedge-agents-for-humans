from __future__ import annotations

import pytest
from fakes import InMemoryApprovalRepository
from test_rework_wp04_r1 import _a2_for, _binding
from test_rework_wp04_r3 import _replaced_envelope_binding
from wp04_helpers import A2_ID, BUYER, OCCURRED_AT, OWNER, SUPPLIERS

from itaa_application.dispatch_service import DispatchService
from itaa_policy.errors import PolicyError


def test_dispatch_service_rejects_replacement_envelope_for_approved_row() -> None:
    repo = InMemoryApprovalRepository()
    dispatch = DispatchService(repo)
    original = _binding()
    repo.append(_a2_for(original))
    allowed = dispatch.authorize(
        A2_ID,
        binding=original,
        supplier_token=SUPPLIERS[0],
        occurred_at=OCCURRED_AT,
        actor=BUYER,
        owner_id=OWNER,
    )
    assert allowed.allowed is True
    assert allowed.envelope is not None
    assert (
        allowed.envelope.envelope_hash.to_primitive()
        == next(
            row
            for row in original.manifest.recipients
            if row["supplierToken"] == SUPPLIERS[0].to_primitive()
        )["envelopeHash"]
    )
    with pytest.raises(PolicyError) as captured:
        dispatch.authorize(
            A2_ID,
            binding=_replaced_envelope_binding(),
            supplier_token=SUPPLIERS[0],
            occurred_at=OCCURRED_AT,
            actor=BUYER,
            owner_id=OWNER,
        )
    assert captured.value.code == "mismatch"
    assert "iv_" not in str(captured.value)
    assert "sha256:" not in str(captured.value)
    assert "alice@" not in str(captured.value)
