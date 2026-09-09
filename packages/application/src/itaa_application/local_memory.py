"""Process-local in-memory adapters. State is lost on restart. Not durable.

Mutating operations run inside :class:`LocalMemoryUnitOfWork`. Each store writes
to a staged copy; ``commit`` publishes every store together and ``rollback``
discards every staged write. Restart durability is unsupported.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from threading import Lock, get_ident
from types import TracebackType
from typing import Literal, Self

from itaa_application.governance_ports import ApprovalResolution
from itaa_application.session_models import BuyerSessionState, GoldenPathSession
from itaa_application.supplier_port import SupplierPort
from itaa_domain.identifiers import ApprovalId, IntentId, SupplierToken
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

PROCESS_LOCAL_ONLY = True
DURABILITY = "unsupported"
RESTART_LOSES_STATE = True


def _capacity_of(port: object) -> int | None:
    remaining = getattr(port, "remaining_capacity", None)
    if type(remaining) is int and not isinstance(remaining, bool):
        return remaining
    return None


def _restore_capacity(port: object, remaining: int) -> None:
    restorer = getattr(port, "restore_capacity", None)
    if callable(restorer):
        restorer(remaining)
        return
    if hasattr(port, "_remaining"):
        object.__setattr__(port, "_remaining", remaining)


@dataclass(frozen=True, slots=True)
class MemoryInspection:
    """Committed process-local state for failure-safety assertions."""

    session_states: Mapping[str, BuyerSessionState]
    authorization_result_refs: Mapping[str, str | None]
    approval_ids: frozenset[str]
    idempotency_states: Mapping[tuple[str, str, str], IdempotencyState]
    idempotency_result_refs: Mapping[tuple[str, str, str], str | None]
    audit_event_ids: tuple[str, ...]
    capacities: Mapping[str, int]


class InMemorySessionRepository:
    """Process-local session store. Restart discards every session."""

    def __init__(self) -> None:
        self._committed: dict[str, GoldenPathSession] = {}
        self._staged: dict[str, GoldenPathSession] | None = None
        self._owner: int | None = None
        self._lock = Lock()

    def _store(self) -> dict[str, GoldenPathSession]:
        if self._staged is not None and self._owner == get_ident():
            return self._staged
        return self._committed

    def get(self, intent_id: IntentId) -> GoldenPathSession | None:
        return self._store().get(intent_id.to_primitive())

    def save(self, session: GoldenPathSession) -> None:
        with self._lock:
            self._store()[session.intent_id.to_primitive()] = session

    def delete(self, intent_id: IntentId) -> None:
        with self._lock:
            self._store().pop(intent_id.to_primitive(), None)

    def list_all(self) -> tuple[GoldenPathSession, ...]:
        return tuple(self._store().values())

    def begin(self) -> None:
        self._staged = dict(self._committed)
        self._owner = get_ident()

    def commit(self) -> None:
        if self._staged is not None:
            self._committed = self._staged
            self._staged = None
            self._owner = None

    def rollback(self) -> None:
        self._staged = None
        self._owner = None

    def committed_sessions(self) -> dict[str, GoldenPathSession]:
        return dict(self._committed)


class InMemoryApprovalRepository:
    def __init__(self) -> None:
        self._committed_grants: dict[str, ApprovalGrant] = {}
        self._committed_revocations: dict[str, ApprovalRevocation] = {}
        self._staged_grants: dict[str, ApprovalGrant] | None = None
        self._staged_revocations: dict[str, ApprovalRevocation] | None = None
        self._owner: int | None = None
        self._lock = Lock()

    def _active(self) -> bool:
        return self._staged_grants is not None and self._owner == get_ident()

    def _grants(self) -> dict[str, ApprovalGrant]:
        return (
            self._staged_grants
            if self._active() and self._staged_grants is not None
            else self._committed_grants
        )

    def _revocations(self) -> dict[str, ApprovalRevocation]:
        if self._active() and self._staged_revocations is not None:
            return self._staged_revocations
        return self._committed_revocations

    def append(self, grant: ApprovalGrant) -> ApprovalGrant:
        with self._lock:
            key = grant.approval_id.to_primitive()
            existing = self._grants().get(key)
            if existing is None:
                self._grants()[key] = grant
                return grant
            if existing != grant:
                raise PolicyConflictError("approval_id", "conflict")
            return existing

    def get(self, approval_id: ApprovalId) -> ApprovalGrant | None:
        return self._grants().get(approval_id.to_primitive())

    def revoke(self, revocation: ApprovalRevocation) -> ApprovalRevocation:
        with self._lock:
            target = revocation.target_id.to_primitive()
            if target not in self._grants():
                raise PolicyError("approval_id", "missing")
            key = revocation.revocation_id.to_primitive()
            existing = self._revocations().get(key)
            if existing is None:
                if target in {
                    item.target_id.to_primitive() for item in self._revocations().values()
                }:
                    raise PolicyConflictError("approval_id", "already_revoked")
                self._revocations()[key] = revocation
                return revocation
            if existing != revocation:
                raise PolicyConflictError("revocation_id", "conflict")
            return existing

    def is_revoked(self, approval_id: ApprovalId) -> bool:
        target = approval_id.to_primitive()
        return any(item.target_id.to_primitive() == target for item in self._revocations().values())

    def resolve(self, approval_id: ApprovalId) -> ApprovalResolution:
        with self._lock:
            grant = self._grants().get(approval_id.to_primitive())
            revoked = any(
                item.target_id.to_primitive() == approval_id.to_primitive()
                for item in self._revocations().values()
            )
            return ApprovalResolution(grant, revoked)

    def begin(self) -> None:
        self._staged_grants = dict(self._committed_grants)
        self._staged_revocations = dict(self._committed_revocations)
        self._owner = get_ident()

    def commit(self) -> None:
        if self._staged_grants is not None:
            self._committed_grants = self._staged_grants
            self._committed_revocations = self._staged_revocations or {}
            self._staged_grants = None
            self._staged_revocations = None
            self._owner = None

    def rollback(self) -> None:
        self._staged_grants = None
        self._staged_revocations = None
        self._owner = None

    def committed_ids(self) -> frozenset[str]:
        return frozenset(self._committed_grants)


class InMemoryIdempotencyRepository:
    def __init__(self) -> None:
        self._committed: dict[tuple[str, str, str], IdempotencyRecord] = {}
        self._staged: dict[tuple[str, str, str], IdempotencyRecord] | None = None
        self._owner: int | None = None
        self._lock = Lock()

    def _store(self) -> dict[tuple[str, str, str], IdempotencyRecord]:
        if self._staged is not None and self._owner == get_ident():
            return self._staged
        return self._committed

    def reserve(
        self,
        scope: IdempotencyScope,
        request_hash: PayloadHash,
        occurred_at: datetime,
        expires_at: datetime,
    ) -> tuple[IdempotencyOutcomeKind, IdempotencyRecord]:
        with self._lock:
            key = scope.to_key()
            current = self._store().get(key)
            if current is None or record_is_expired(current, occurred_at):
                record = IdempotencyRecord(
                    scope=scope,
                    request_hash=request_hash,
                    created_at=occurred_at,
                    expires_at=expires_at,
                    state=IdempotencyState.PENDING,
                )
                self._store()[key] = record
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
            self._store()[key] = record
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
            current = self._store().get(key)
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
            self._store()[key] = record
            return record

    def fail(
        self,
        scope: IdempotencyScope,
        request_hash: PayloadHash,
        occurred_at: datetime,
    ) -> IdempotencyRecord:
        with self._lock:
            key = scope.to_key()
            current = self._store().get(key)
            if current is None or current.request_hash != request_hash:
                raise PolicyConflictError("idempotency_key", "request_mismatch")
            if current.state is IdempotencyState.COMPLETED:
                raise PolicyConflictError("idempotency_key", "already_completed")
            record = replace(current, state=IdempotencyState.FAILED)
            self._store()[key] = record
            return record

    def begin(self) -> None:
        self._staged = dict(self._committed)
        self._owner = get_ident()

    def commit(self) -> None:
        if self._staged is not None:
            self._committed = self._staged
            self._staged = None
            self._owner = None

    def rollback(self) -> None:
        self._staged = None
        self._owner = None

    def committed_records(self) -> dict[tuple[str, str, str], IdempotencyRecord]:
        return dict(self._committed)


class InMemoryAuditSink:
    def __init__(self) -> None:
        self._committed_records: list[AuditRecord] = []
        self._committed_by_id: dict[str, AuditRecord] = {}
        self._committed_tails: dict[str, PayloadHash] = {}
        self._staged_records: list[AuditRecord] | None = None
        self._staged_by_id: dict[str, AuditRecord] | None = None
        self._staged_tails: dict[str, PayloadHash] | None = None
        self._owner: int | None = None
        self._lock = Lock()

    def _active(self) -> bool:
        return self._staged_records is not None and self._owner == get_ident()

    @property
    def records(self) -> list[AuditRecord]:
        return self._records()

    def _records(self) -> list[AuditRecord]:
        return (
            self._staged_records
            if self._active() and self._staged_records is not None
            else self._committed_records
        )

    def _by_id(self) -> dict[str, AuditRecord]:
        return (
            self._staged_by_id
            if self._active() and self._staged_by_id is not None
            else self._committed_by_id
        )

    def _tails(self) -> dict[str, PayloadHash]:
        return (
            self._staged_tails
            if self._active() and self._staged_tails is not None
            else self._committed_tails
        )

    def append(self, record: AuditRecord, *, stream_id: str | None = None) -> AuditRecord:
        with self._lock:
            existing = self._by_id().get(record.event_id)
            if existing is not None:
                if existing != record:
                    raise AuditConflictError("event_id", "conflict")
                return existing
            if stream_id is not None:
                tail = self._tails().get(stream_id)
                if tail is None:
                    if record.previous_event_hash is not None:
                        raise AuditConflictError("previous_event_hash", "stream_empty")
                elif record.previous_event_hash != tail:
                    raise AuditConflictError("previous_event_hash", "chain_mismatch")
            self._by_id()[record.event_id] = record
            self._records().append(record)
            if stream_id is not None:
                self._tails()[stream_id] = record.event_hash
            return record

    def tail_hash(self, stream_id: str) -> PayloadHash | None:
        return self._tails().get(stream_id)

    def begin(self) -> None:
        self._staged_records = list(self._committed_records)
        self._staged_by_id = dict(self._committed_by_id)
        self._staged_tails = dict(self._committed_tails)
        self._owner = get_ident()

    def commit(self) -> None:
        if self._staged_records is not None:
            self._committed_records = self._staged_records
            self._committed_by_id = self._staged_by_id or {}
            self._committed_tails = self._staged_tails or {}
            self._staged_records = None
            self._staged_by_id = None
            self._staged_tails = None
            self._owner = None

    def rollback(self) -> None:
        self._staged_records = None
        self._staged_by_id = None
        self._staged_tails = None
        self._owner = None

    def committed_event_ids(self) -> tuple[str, ...]:
        return tuple(item.event_id for item in self._committed_records)

    def committed_records(self) -> tuple[AuditRecord, ...]:
        return tuple(self._committed_records)


@dataclass(frozen=True, slots=True)
class ReplaceRecord:
    request_hash: str
    original_intent_id: str
    replacement_intent_id: str


class InMemoryReplaceLog:
    """Closed replace idempotency without extending policy operation enums."""

    def __init__(self) -> None:
        self._committed: dict[tuple[str, str], ReplaceRecord] = {}
        self._staged: dict[tuple[str, str], ReplaceRecord] | None = None
        self._owner: int | None = None
        self._lock = Lock()

    def _store(self) -> dict[tuple[str, str], ReplaceRecord]:
        if self._staged is not None and self._owner == get_ident():
            return self._staged
        return self._committed

    def get(self, portfolio_id: str, idempotency_key: str) -> ReplaceRecord | None:
        return self._store().get((portfolio_id, idempotency_key))

    def put(self, portfolio_id: str, idempotency_key: str, record: ReplaceRecord) -> None:
        with self._lock:
            self._store()[(portfolio_id, idempotency_key)] = record

    def begin(self) -> None:
        self._staged = dict(self._committed)
        self._owner = get_ident()

    def commit(self) -> None:
        if self._staged is not None:
            self._committed = self._staged
            self._staged = None
            self._owner = None

    def rollback(self) -> None:
        self._staged = None
        self._owner = None


class LocalMemoryUnitOfWork:
    """Copy-on-write unit of work for every process-local participating store.

    ``transaction(intent_id)`` takes a per-intent lock so two worker threads
    cannot both pass the same state check and publish conflicting transitions.
    Shared-store snapshots are taken under a process-wide lock so concurrent
    different intents cannot clobber each other's commit.
    """

    def __init__(
        self,
        *,
        sessions: InMemorySessionRepository | None = None,
        approvals: InMemoryApprovalRepository | None = None,
        idempotency: InMemoryIdempotencyRepository | None = None,
        audit: InMemoryAuditSink | None = None,
        replace_log: InMemoryReplaceLog | None = None,
    ) -> None:
        self.sessions = sessions or InMemorySessionRepository()
        self.approvals = approvals or InMemoryApprovalRepository()
        self.idempotency = idempotency or InMemoryIdempotencyRepository()
        self.audit = audit or InMemoryAuditSink()
        self.replace_log = replace_log or InMemoryReplaceLog()
        self._capacity_ports: dict[str, object] = {}
        self._capacity_snapshot: dict[str, int] = {}
        self._intent_locks: dict[str, Lock] = {}
        self._registry_lock = Lock()
        self._publish_lock = Lock()
        self._active = 0

    def attach_capacity_ports(self, ports: Mapping[SupplierToken, SupplierPort]) -> None:
        self._capacity_ports = {token.to_primitive(): port for token, port in ports.items()}

    def capture_capacity(self) -> None:
        self._capacity_snapshot = {}
        for token, port in self._capacity_ports.items():
            remaining = _capacity_of(port)
            if remaining is not None:
                self._capacity_snapshot[token] = remaining

    def inspect(self) -> MemoryInspection:
        sessions = self.sessions.committed_sessions()
        records = self.idempotency.committed_records()
        capacities: dict[str, int] = {}
        for token, port in self._capacity_ports.items():
            remaining = _capacity_of(port)
            if remaining is not None:
                capacities[token] = remaining
        return MemoryInspection(
            session_states={key: item.state for key, item in sessions.items()},
            authorization_result_refs={
                key: None
                if item.authorization_result_ref is None
                else item.authorization_result_ref.to_primitive()
                for key, item in sessions.items()
            },
            approval_ids=self.approvals.committed_ids(),
            idempotency_states={key: item.state for key, item in records.items()},
            idempotency_result_refs={
                key: None if item.result_ref is None else item.result_ref.to_primitive()
                for key, item in records.items()
            },
            audit_event_ids=self.audit.committed_event_ids(),
            capacities=capacities,
        )

    def _lock_for(self, intent_id: IntentId) -> Lock:
        key = intent_id.to_primitive()
        with self._registry_lock:
            existing = self._intent_locks.get(key)
            if existing is None:
                existing = Lock()
                self._intent_locks[key] = existing
            return existing

    def _begin_locked(self) -> None:
        self.sessions.begin()
        self.approvals.begin()
        self.idempotency.begin()
        self.audit.begin()
        self.replace_log.begin()
        self._capacity_snapshot = {}
        for token, port in self._capacity_ports.items():
            remaining = _capacity_of(port)
            if remaining is not None:
                self._capacity_snapshot[token] = remaining
        self._active += 1

    def _commit_locked(self) -> None:
        self.sessions.commit()
        self.approvals.commit()
        self.idempotency.commit()
        self.audit.commit()
        self.replace_log.commit()
        self._capacity_snapshot = {}
        self._active -= 1

    def _rollback_locked(self) -> None:
        self.sessions.rollback()
        self.approvals.rollback()
        self.idempotency.rollback()
        self.audit.rollback()
        self.replace_log.rollback()
        for token, remaining in self._capacity_snapshot.items():
            port = self._capacity_ports.get(token)
            if port is not None:
                _restore_capacity(port, remaining)
        self._capacity_snapshot = {}
        self._active -= 1

    def transaction(self, intent_id: IntentId) -> LocalMemoryTransaction:
        return LocalMemoryTransaction(self, (intent_id,))

    def transaction_many(self, intent_ids: tuple[IntentId, ...]) -> LocalMemoryTransaction:
        return LocalMemoryTransaction(self, intent_ids)


class LocalMemoryTransaction:
    """Class-based context manager so frozen ApplicationError can propagate.

    ``@contextmanager`` generators assign ``__traceback__`` on the exception
    object; frozen dataclass errors reject that assignment.
    """

    def __init__(
        self, unit_of_work: LocalMemoryUnitOfWork, intent_ids: tuple[IntentId, ...]
    ) -> None:
        self._unit_of_work = unit_of_work
        unique = tuple(dict.fromkeys(intent_ids))
        self._intent_ids = tuple(sorted(unique, key=lambda item: item.to_primitive()))
        self._intent_locks: list[Lock] = []

    def __enter__(self) -> Self:
        acquired: list[Lock] = []
        try:
            for intent_id in self._intent_ids:
                lock = self._unit_of_work._lock_for(intent_id)
                lock.acquire()
                acquired.append(lock)
            self._intent_locks = acquired
            self._unit_of_work._publish_lock.acquire()
            try:
                self._unit_of_work._begin_locked()
            except BaseException:
                self._unit_of_work._publish_lock.release()
                raise
        except BaseException:
            for lock in reversed(acquired):
                lock.release()
            raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        del exc_type, traceback
        try:
            if exc is None:
                self._unit_of_work._commit_locked()
            else:
                self._unit_of_work._rollback_locked()
            return False
        finally:
            self._unit_of_work._publish_lock.release()
            for lock in reversed(self._intent_locks):
                lock.release()
            self._intent_locks = []
