"""Application-facing governance ports. No storage, HTTP, or adapter types."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from itaa_domain.identifiers import ApprovalId
from itaa_domain.value_objects import PayloadHash
from itaa_observability.audit import AuditRecord
from itaa_policy.approvals import ApprovalGrant, ApprovalRevocation
from itaa_policy.idempotency import (
    IdempotencyOutcomeKind,
    IdempotencyRecord,
    IdempotencyScope,
    ResultRef,
)


@dataclass(frozen=True, slots=True)
class ApprovalResolution:
    grant: ApprovalGrant | None
    revoked: bool


class ApprovalRepository(Protocol):
    def append(self, grant: ApprovalGrant) -> ApprovalGrant:
        """Append-only. Byte-identical replay returns the existing grant."""
        ...

    def get(self, approval_id: ApprovalId) -> ApprovalGrant | None: ...

    def revoke(self, revocation: ApprovalRevocation) -> ApprovalRevocation: ...

    def is_revoked(self, approval_id: ApprovalId) -> bool: ...

    def resolve(self, approval_id: ApprovalId) -> ApprovalResolution:
        """Atomically load grant and revocation/effective state. Not get-then-is_revoked."""
        ...


class AtomicIdempotencyRepository(Protocol):
    def reserve(
        self,
        scope: IdempotencyScope,
        request_hash: PayloadHash,
        occurred_at: datetime,
        expires_at: datetime,
    ) -> tuple[IdempotencyOutcomeKind, IdempotencyRecord]:
        """Atomically reserve or classify the key. Must not be get-then-put."""
        ...

    def complete(
        self,
        scope: IdempotencyScope,
        request_hash: PayloadHash,
        response_hash: PayloadHash,
        result_ref: ResultRef,
        occurred_at: datetime,
    ) -> IdempotencyRecord: ...

    def fail(
        self,
        scope: IdempotencyScope,
        request_hash: PayloadHash,
        occurred_at: datetime,
    ) -> IdempotencyRecord: ...


class ApplicationAuditSink(Protocol):
    def append(self, record: AuditRecord, *, stream_id: str | None = None) -> AuditRecord: ...

    def tail_hash(self, stream_id: str) -> PayloadHash | None: ...
