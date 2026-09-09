"""Authorize supplier dispatch only when A2 approval and envelope membership both succeed."""

from __future__ import annotations

from datetime import datetime

from itaa_application.governance_ports import ApprovalRepository
from itaa_domain.identifiers import ActorId, ApprovalId, SupplierToken
from itaa_domain.value_objects import ActorRef
from itaa_policy.approvals import ApprovalDecision, ApprovalDenyReason
from itaa_policy.envelopes import DispatchAuthorization, SolicitationBinding, authorize_dispatch


class DispatchService:
    """Application dispatch-authorization boundary.

    Resolves grant plus revocation state atomically, then evaluates the snapshot
    against the envelope/scope binding. Policy ``authorize_dispatch`` does not
    prove repository revocation.
    """

    def __init__(self, repository: ApprovalRepository) -> None:
        self._repository = repository

    def authorize(
        self,
        approval_id: ApprovalId | None,
        *,
        binding: SolicitationBinding,
        supplier_token: SupplierToken,
        occurred_at: datetime,
        actor: ActorRef,
        owner_id: ActorId,
    ) -> DispatchAuthorization:
        if approval_id is None:
            return authorize_dispatch(
                None,
                binding=binding,
                supplier_token=supplier_token,
                occurred_at=occurred_at,
                actor=actor,
                owner_id=owner_id,
            )
        resolution = self._repository.resolve(approval_id)
        if resolution.revoked:
            kind = None if resolution.grant is None else resolution.grant.kind
            return DispatchAuthorization(
                False,
                ApprovalDecision(False, ApprovalDenyReason.INACTIVE, approval_id, kind),
                None,
            )
        return authorize_dispatch(
            resolution.grant,
            binding=binding,
            supplier_token=supplier_token,
            occurred_at=occurred_at,
            actor=actor,
            owner_id=owner_id,
        )
