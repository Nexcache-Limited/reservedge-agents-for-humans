"""Idempotency request binding types. Storage ports live in application."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from itaa_domain.identifiers import CROCKFORD_BODY, ActorId, IdempotencyKey
from itaa_domain.value_objects import PayloadHash, require_exact_enum, require_utc
from itaa_policy.canonical import SEPARATOR_IDEMPOTENCY_REQUEST, hash_canonical
from itaa_policy.errors import PolicyError


class IdempotencyOperation(StrEnum):
    CREATE_INTENT = "create_intent"
    ACCEPT_OFFER = "accept_offer"
    AUTHORIZE_TRANSACTION = "authorize_transaction"


class IdempotencyState(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class IdempotencyOutcomeKind(StrEnum):
    RESERVED = "reserved"
    IN_PROGRESS = "in_progress"
    REPLAYED = "replayed"
    CONFLICT = "conflict"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED_REPLACED = "expired_replaced"


@dataclass(frozen=True, slots=True)
class ResultRef:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or isinstance(self.value, bool):
            raise PolicyError("result_ref", "must_be_string")
        if not re.fullmatch("rr_" + CROCKFORD_BODY, self.value):
            raise PolicyError("result_ref", "invalid_opaque_syntax")

    def to_primitive(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class IdempotencyScope:
    actor_id: ActorId
    operation: IdempotencyOperation
    key: IdempotencyKey

    def __post_init__(self) -> None:
        if type(self.actor_id) is not ActorId:
            raise PolicyError("actor_id", "invalid_opaque_syntax")
        require_exact_enum(self.operation, IdempotencyOperation, "operation")
        if type(self.key) is not IdempotencyKey:
            raise PolicyError("idempotency_key", "invalid_opaque_syntax")

    def to_key(self) -> tuple[str, str, str]:
        return (
            self.actor_id.to_primitive(),
            self.operation.value,
            self.key.to_primitive(),
        )


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    scope: IdempotencyScope
    request_hash: PayloadHash
    created_at: datetime
    expires_at: datetime
    state: IdempotencyState
    response_hash: PayloadHash | None = None
    result_ref: ResultRef | None = None

    def __post_init__(self) -> None:
        require_exact_enum(self.state, IdempotencyState, "state")
        created = require_utc(self.created_at, "created_at")
        expires = require_utc(self.expires_at, "expires_at")
        if expires <= created:
            raise PolicyError("expires_at", "must_follow_created")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "expires_at", expires)
        if self.result_ref is not None and type(self.result_ref) is not ResultRef:
            raise PolicyError("result_ref", "invalid_type")
        if self.state is IdempotencyState.COMPLETED:
            if self.response_hash is None:
                raise PolicyError("response_hash", "required")
            if self.result_ref is None:
                raise PolicyError("result_ref", "required")


def hash_idempotency_request(request: object) -> PayloadHash:
    return hash_canonical(SEPARATOR_IDEMPOTENCY_REQUEST, request)


def record_is_expired(record: IdempotencyRecord, occurred_at: datetime) -> bool:
    instant = require_utc(occurred_at, "occurred_at")
    return instant >= record.expires_at
