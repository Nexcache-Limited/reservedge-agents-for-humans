"""Atomic idempotency application service. No HTTP or storage types."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime

from itaa_application.governance_ports import AtomicIdempotencyRepository
from itaa_domain.value_objects import PayloadHash, require_utc
from itaa_policy.canonical import SEPARATOR_IDEMPOTENCY_REQUEST, hash_canonical
from itaa_policy.errors import PolicyConflictError, PolicyError
from itaa_policy.idempotency import (
    IdempotencyOutcomeKind,
    IdempotencyRecord,
    IdempotencyScope,
    ResultRef,
    hash_idempotency_request,
)


@dataclass(frozen=True, slots=True)
class IdempotencyResult:
    """Reference-only public result. First completion and replay return the same ResultRef."""

    kind: IdempotencyOutcomeKind
    record: IdempotencyRecord
    result_ref: ResultRef | None


class IdempotencyService:
    """Deterministic expiry and failure rules:

    - Expired records are never returned as current. A later live request for the
      same scope atomically replaces the expired record and may execute once.
    - FAILED records with the same request hash may be retried by a replacement
      reservation. A different request hash conflicts unless the failed record
      is expired. Completion cannot produce two distinct completed results.
    - The public result is a typed ResultRef. Raw effect bodies are hashed, not stored
      or returned, so completed replay cannot leak a sensitive payload.
    """

    def __init__(self, repository: AtomicIdempotencyRepository) -> None:
        self._repository = repository

    def execute(
        self,
        *,
        scope: IdempotencyScope,
        request: object,
        occurred_at: datetime,
        expires_at: datetime,
        result_ref: ResultRef,
        effect: Callable[[], Mapping[str, object]],
    ) -> IdempotencyResult:
        require_utc(occurred_at, "occurred_at")
        if type(result_ref) is not ResultRef:
            raise PolicyError("result_ref", "invalid_type")
        request_hash = hash_idempotency_request(request)
        kind, record = self._repository.reserve(scope, request_hash, occurred_at, expires_at)
        if kind is IdempotencyOutcomeKind.CONFLICT:
            raise PolicyConflictError("idempotency_key", "request_mismatch")
        if kind is IdempotencyOutcomeKind.IN_PROGRESS:
            return IdempotencyResult(kind, record, None)
        if kind is IdempotencyOutcomeKind.REPLAYED:
            return IdempotencyResult(kind, record, record.result_ref)
        if kind not in {IdempotencyOutcomeKind.RESERVED, IdempotencyOutcomeKind.EXPIRED_REPLACED}:
            raise PolicyError("idempotency", "unsupported_outcome")
        try:
            response = dict(effect())
            response_hash = hash_canonical(SEPARATOR_IDEMPOTENCY_REQUEST, {"response": response})
        except Exception:
            self._repository.fail(scope, request_hash, occurred_at)
            raise
        completed = self._repository.complete(
            scope,
            request_hash,
            response_hash,
            result_ref,
            occurred_at,
        )
        return IdempotencyResult(IdempotencyOutcomeKind.COMPLETED, completed, completed.result_ref)

    def complete_only(
        self,
        *,
        scope: IdempotencyScope,
        request_hash: PayloadHash,
        response_hash: PayloadHash,
        result_ref: ResultRef,
        occurred_at: datetime,
    ) -> IdempotencyRecord:
        if type(result_ref) is not ResultRef:
            raise PolicyError("result_ref", "invalid_type")
        return self._repository.complete(
            scope, request_hash, response_hash, result_ref, occurred_at
        )
