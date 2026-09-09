"""Issue, validate, and revoke A1–A4 approvals through an append-only port."""

from __future__ import annotations

from itaa_application.governance_ports import ApprovalRepository
from itaa_domain.identifiers import ApprovalId
from itaa_domain.value_objects import require_utc
from itaa_policy.approvals import (
    ApprovalDecision,
    ApprovalDenyReason,
    ApprovalGrant,
    ApprovalRequest,
    ApprovalRevocation,
    validate_approval,
)
from itaa_policy.errors import PolicyError


class ApprovalService:
    def __init__(self, repository: ApprovalRepository) -> None:
        self._repository = repository

    def issue(self, grant: ApprovalGrant) -> ApprovalGrant:
        return self._repository.append(grant)

    def validate(self, approval_id: ApprovalId, request: ApprovalRequest) -> ApprovalDecision:
        resolution = self._repository.resolve(approval_id)
        if resolution.revoked:
            kind = None if resolution.grant is None else resolution.grant.kind
            return ApprovalDecision(False, ApprovalDenyReason.INACTIVE, approval_id, kind)
        return validate_approval(resolution.grant, request)

    def revoke(self, revocation: ApprovalRevocation) -> ApprovalRevocation:
        require_utc(revocation.occurred_at, "occurred_at")
        current = self._repository.get(revocation.target_id)
        if current is None:
            raise PolicyError("approval_id", "missing")
        return self._repository.revoke(revocation)

    def deny_missing(self, request: ApprovalRequest) -> ApprovalDecision:
        return ApprovalDecision(False, ApprovalDenyReason.MISSING, None, request.kind)
