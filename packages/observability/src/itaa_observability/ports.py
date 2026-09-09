"""Append-only audit sink port. Implementations belong in later adapters."""

from __future__ import annotations

from typing import Protocol

from itaa_domain.value_objects import PayloadHash
from itaa_observability.audit import AuditRecord
from itaa_observability.errors import AuditConflictError


class AuditSink(Protocol):
    def append(self, record: AuditRecord, *, stream_id: str | None = None) -> AuditRecord:
        """Atomically append. Identical replay returns the existing record."""
        ...

    def tail_hash(self, stream_id: str) -> PayloadHash | None:
        """Return the latest event hash for an optional chain stream."""
        ...


def tail_hash_type() -> object:
    """Canonical tail type shared with the application audit port."""

    return PayloadHash | None


def require_no_mutation_api(sink: object) -> None:
    for name in ("update", "delete", "remove", "overwrite"):
        if hasattr(sink, name):
            raise AuditConflictError("sink", "mutation_api_forbidden")
