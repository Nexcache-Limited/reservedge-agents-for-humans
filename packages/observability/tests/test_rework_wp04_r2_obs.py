from __future__ import annotations

from typing import get_type_hints

from itaa_domain.value_objects import PayloadHash
from itaa_observability.ports import AuditSink, tail_hash_type


def test_observability_tail_hash_uses_payload_hash() -> None:
    assert get_type_hints(AuditSink.tail_hash)["return"] == PayloadHash | None
    assert tail_hash_type() == PayloadHash | None
    assert get_type_hints(AuditSink.tail_hash)["return"] == tail_hash_type()
