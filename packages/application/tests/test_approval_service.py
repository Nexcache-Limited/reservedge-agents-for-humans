from __future__ import annotations

import pytest
from fakes import InMemoryApprovalRepository
from test_approvals import _a2, _request_from
from wp04_helpers import A2_ID, CORRELATION, OCCURRED_AT, REVOKE_ID

from itaa_application.approval_service import ApprovalService
from itaa_policy.approvals import ApprovalDenyReason, ApprovalRevocation
from itaa_policy.errors import PolicyConflictError


def test_issue_replay_and_conflict() -> None:
    service = ApprovalService(InMemoryApprovalRepository())
    grant = _a2()
    assert service.issue(grant) == grant
    assert service.issue(grant) == grant
    mutated = _a2(count=2)
    with pytest.raises(PolicyConflictError):
        service.issue(mutated)


def test_validate_and_revoke_without_mutating_history() -> None:
    repo = InMemoryApprovalRepository()
    service = ApprovalService(repo)
    grant = _a2()
    service.issue(grant)
    allowed = service.validate(A2_ID, _request_from(grant))
    assert allowed.allowed is True
    service.revoke(
        ApprovalRevocation(
            revocation_id=REVOKE_ID,
            target_id=A2_ID,
            occurred_at=OCCURRED_AT,
            correlation_id=CORRELATION,
        )
    )
    denied = service.validate(A2_ID, _request_from(grant))
    assert denied.reason is ApprovalDenyReason.INACTIVE
    assert repo.get(A2_ID) == grant
