"""Test-only in-memory repositories. Not production adapters."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from threading import Lock

from itaa_application.governance_ports import ApprovalResolution
from itaa_domain.identifiers import ApprovalId
from itaa_domain.value_objects import PayloadHash
from itaa_observability.audit import AuditRecord
from itaa_observability.errors import AuditConflictError
from itaa_policy.approvals import ApprovalGrant, ApprovalRevocation
from itaa_policy.errors import PolicyConflictError, PolicyError
from itaa_policy.idempotency import (
    IdempotencyOutcomeKind,
    IdempotencyRecord,
    IdempotencyScope,
    IdempotencyState,
    ResultRef,
    record_is_expired,
)


class InMemoryApprovalRepository:
    def __init__(self) -> None:
        self._grants: dict[str, ApprovalGrant] = {}
        self._revocations: dict[str, ApprovalRevocation] = {}
        self._lock = Lock()

    def append(self, grant: ApprovalGrant) -> ApprovalGrant:
        with self._lock:
            key = grant.approval_id.to_primitive()
            existing = self._grants.get(key)
            if existing is None:
                self._grants[key] = grant
                return grant
            if existing != grant:
                raise PolicyConflictError("approval_id", "conflict")
            return existing

    def get(self, approval_id: ApprovalId) -> ApprovalGrant | None:
        return self._grants.get(approval_id.to_primitive())

    def revoke(self, revocation: ApprovalRevocation) -> ApprovalRevocation:
        with self._lock:
            target = revocation.target_id.to_primitive()
            if target not in self._grants:
                raise PolicyError("approval_id", "missing")
            key = revocation.revocation_id.to_primitive()
            existing = self._revocations.get(key)
            if existing is None:
                if target in {item.target_id.to_primitive() for item in self._revocations.values()}:
                    raise PolicyConflictError("approval_id", "already_revoked")
                self._revocations[key] = revocation
                return revocation
            if existing != revocation:
                raise PolicyConflictError("revocation_id", "conflict")
            return existing

    def is_revoked(self, approval_id: ApprovalId) -> bool:
        target = approval_id.to_primitive()
        return any(item.target_id.to_primitive() == target for item in self._revocations.values())

    def resolve(self, approval_id: ApprovalId) -> ApprovalResolution:
        with self._lock:
            grant = self._grants.get(approval_id.to_primitive())
            revoked = any(
                item.target_id.to_primitive() == approval_id.to_primitive()
                for item in self._revocations.values()
            )
            return ApprovalResolution(grant, revoked)


class InMemoryIdempotencyRepository:
    def __init__(self) -> None:
        self._records: dict[tuple[str, str, str], IdempotencyRecord] = {}
        self._lock = Lock()

    def reserve(
        self,
        scope: IdempotencyScope,
        request_hash: PayloadHash,
        occurred_at: datetime,
        expires_at: datetime,
    ) -> tuple[IdempotencyOutcomeKind, IdempotencyRecord]:
        with self._lock:
            key = scope.to_key()
            current = self._records.get(key)
            if current is None or record_is_expired(current, occurred_at):
                record = IdempotencyRecord(
                    scope=scope,
                    request_hash=request_hash,
                    created_at=occurred_at,
                    expires_at=expires_at,
                    state=IdempotencyState.PENDING,
                )
                self._records[key] = record
                kind = (
                    IdempotencyOutcomeKind.RESERVED
                    if current is None
                    else IdempotencyOutcomeKind.EXPIRED_REPLACED
                )
                return kind, record
            if current.request_hash != request_hash:
                return IdempotencyOutcomeKind.CONFLICT, current
            if current.state is IdempotencyState.PENDING:
                return IdempotencyOutcomeKind.IN_PROGRESS, current
            if current.state is IdempotencyState.COMPLETED:
                return IdempotencyOutcomeKind.REPLAYED, current
            record = replace(current, state=IdempotencyState.PENDING, request_hash=request_hash)
            self._records[key] = record
            return IdempotencyOutcomeKind.RESERVED, record

    def complete(
        self,
        scope: IdempotencyScope,
        request_hash: PayloadHash,
        response_hash: PayloadHash,
        result_ref: ResultRef,
        occurred_at: datetime,
    ) -> IdempotencyRecord:
        with self._lock:
            key = scope.to_key()
            current = self._records.get(key)
            if current is None:
                raise PolicyError("idempotency_key", "missing")
            if current.request_hash != request_hash:
                raise PolicyConflictError("idempotency_key", "request_mismatch")
            if current.state is IdempotencyState.COMPLETED:
                if current.response_hash != response_hash or current.result_ref != result_ref:
                    raise PolicyConflictError("idempotency_key", "completion_mismatch")
                return current
            if current.state is not IdempotencyState.PENDING:
                raise PolicyConflictError("idempotency_key", "not_pending")
            record = replace(
                current,
                state=IdempotencyState.COMPLETED,
                response_hash=response_hash,
                result_ref=result_ref,
            )
            self._records[key] = record
            return record

    def fail(
        self,
        scope: IdempotencyScope,
        request_hash: PayloadHash,
        occurred_at: datetime,
    ) -> IdempotencyRecord:
        with self._lock:
            key = scope.to_key()
            current = self._records.get(key)
            if current is None or current.request_hash != request_hash:
                raise PolicyConflictError("idempotency_key", "request_mismatch")
            if current.state is IdempotencyState.COMPLETED:
                raise PolicyConflictError("idempotency_key", "already_completed")
            record = replace(current, state=IdempotencyState.FAILED)
            self._records[key] = record
            return record


class InMemoryAuditSink:
    def __init__(self) -> None:
        self.records: list[AuditRecord] = []
        self._by_id: dict[str, AuditRecord] = {}
        self._tails: dict[str, PayloadHash] = {}
        self._lock = Lock()

    def append(self, record: AuditRecord, *, stream_id: str | None = None) -> AuditRecord:
        with self._lock:
            existing = self._by_id.get(record.event_id)
            if existing is not None:
                if existing != record:
                    raise AuditConflictError("event_id", "conflict")
                return existing
            if stream_id is not None:
                tail = self._tails.get(stream_id)
                if tail is None:
                    if record.previous_event_hash is not None:
                        raise AuditConflictError("previous_event_hash", "stream_empty")
                elif record.previous_event_hash != tail:
                    raise AuditConflictError("previous_event_hash", "chain_mismatch")
            self._by_id[record.event_id] = record
            self.records.append(record)
            if stream_id is not None:
                self._tails[stream_id] = record.event_hash
            return record

    def tail_hash(self, stream_id: str) -> PayloadHash | None:
        return self._tails.get(stream_id)
