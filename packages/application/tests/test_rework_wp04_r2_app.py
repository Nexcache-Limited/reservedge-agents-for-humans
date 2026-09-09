from __future__ import annotations

import inspect
from typing import get_type_hints

import pytest
from fakes import InMemoryApprovalRepository, InMemoryIdempotencyRepository
from test_rework_wp04_r1 import _a2_for, _binding
from wp04_helpers import (
    A2_ID,
    BUYER,
    CORRELATION,
    EXPIRES_AT,
    OCCURRED_AT,
    OWNER,
    REVOKE_ID,
    SUPPLIERS,
)

from itaa_application.dispatch_service import DispatchService
from itaa_application.governance_ports import ApplicationAuditSink, ApprovalResolution
from itaa_application.idempotency_service import IdempotencyService
from itaa_domain.identifiers import ActorId, ApprovalId, IdempotencyKey
from itaa_domain.value_objects import PayloadHash
from itaa_observability.ports import AuditSink, tail_hash_type
from itaa_policy.approvals import ApprovalDenyReason, ApprovalGrant, ApprovalRevocation
from itaa_policy.errors import PolicyError
from itaa_policy.idempotency import (
    IdempotencyOperation,
    IdempotencyOutcomeKind,
    IdempotencyScope,
    IdempotencyState,
    ResultRef,
)


class _SpyApprovalRepository(InMemoryApprovalRepository):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []

    def get(self, approval_id: ApprovalId) -> ApprovalGrant | None:
        self.calls.append("get")
        return super().get(approval_id)

    def is_revoked(self, approval_id: ApprovalId) -> bool:
        self.calls.append("is_revoked")
        return super().is_revoked(approval_id)

    def resolve(self, approval_id: ApprovalId) -> ApprovalResolution:
        self.calls.append("resolve")
        return super().resolve(approval_id)


def test_dispatch_service_uses_one_atomic_resolve() -> None:
    repo = _SpyApprovalRepository()
    dispatch = DispatchService(repo)
    binding = _binding()
    grant = _a2_for(binding)
    repo.append(grant)
    repo.calls.clear()
    allowed = dispatch.authorize(
        A2_ID,
        binding=binding,
        supplier_token=SUPPLIERS[0],
        occurred_at=OCCURRED_AT,
        actor=BUYER,
        owner_id=OWNER,
    )
    assert allowed.allowed is True
    assert repo.calls == ["resolve"]
    source = inspect.getsource(DispatchService.authorize)
    assert ".get(" not in source
    assert "is_revoked" not in source
    assert ".resolve(" in source
    repo.revoke(
        ApprovalRevocation(
            revocation_id=REVOKE_ID,
            target_id=A2_ID,
            occurred_at=OCCURRED_AT,
            correlation_id=CORRELATION,
        )
    )
    repo.calls.clear()
    denied = dispatch.authorize(
        A2_ID,
        binding=binding,
        supplier_token=SUPPLIERS[0],
        occurred_at=OCCURRED_AT,
        actor=BUYER,
        owner_id=OWNER,
    )
    assert denied.allowed is False
    assert denied.envelope is None
    assert denied.decision.reason is ApprovalDenyReason.INACTIVE
    assert repo.calls == ["resolve"]


def _idempotency_scope() -> IdempotencyScope:
    return IdempotencyScope(
        actor_id=ActorId("ar_01k2m3n4p5q6r7s8t9v0w1x2k1"),
        operation=IdempotencyOperation.AUTHORIZE_TRANSACTION,
        key=IdempotencyKey("ik_01k2m3n4p5q6r7s8t9v0w1x2g1"),
    )


@pytest.mark.parametrize(
    "bad_response",
    [
        {"amount": 1.5},
        {"nested": {1: "x"}},
    ],
)
def test_response_hash_failure_is_retryable_not_pending(bad_response: dict[object, object]) -> None:
    repo = InMemoryIdempotencyRepository()
    service = IdempotencyService(repo)
    scope = _idempotency_scope()
    request = {"action": "reserve_parking", "amountMinor": 11900}
    result_ref = ResultRef("rr_01k2m3n4p5q6r7s8t9v0w1x2r1")
    with pytest.raises(PolicyError) as captured:
        service.execute(
            scope=scope,
            request=request,
            occurred_at=OCCURRED_AT,
            expires_at=EXPIRES_AT,
            result_ref=result_ref,
            effect=lambda: bad_response,  # type: ignore[arg-type, return-value]
        )
    text = str(captured.value)
    assert "1.5" not in text
    assert "alice@" not in text
    stored = repo._records[scope.to_key()]
    assert stored.state is IdempotencyState.FAILED
    calls: list[int] = []
    completed = service.execute(
        scope=scope,
        request=request,
        occurred_at=OCCURRED_AT,
        expires_at=EXPIRES_AT,
        result_ref=result_ref,
        effect=lambda: calls.append(1) or {"status": "ok"},
    )
    assert completed.kind is IdempotencyOutcomeKind.COMPLETED
    assert completed.result_ref == result_ref
    assert calls == [1]


def test_audit_ports_share_payload_hash_tail_type() -> None:
    expected = tail_hash_type()
    assert get_type_hints(AuditSink.tail_hash)["return"] == expected
    assert get_type_hints(ApplicationAuditSink.tail_hash)["return"] == expected
    assert expected == PayloadHash | None
