from __future__ import annotations

import pytest
from fakes import InMemoryAuditSink
from test_rework_wp03_r2 import _canonical_event
from wp04_helpers import CORRELATION, INVITATIONS, OCCURRED_AT, RESOURCE_INTENT, audit_id

from itaa_application.audit_service import AuditService
from itaa_domain.events import EventType
from itaa_domain.identifiers import ActorId
from itaa_domain.value_objects import ActorType, Version
from itaa_observability.audit import (
    AuditAction,
    AuditDecisionResult,
    AuditReason,
    AuditResourceType,
)
from itaa_observability.errors import AuditConflictError
from itaa_observability.ports import require_no_mutation_api


def test_all_domain_event_types_project_and_append() -> None:
    sink = InMemoryAuditSink()
    service = AuditService(sink)
    require_no_mutation_api(sink)
    previous = None
    for index, event_type in enumerate(EventType, start=1):
        record = service.append_domain_event(
            _canonical_event(event_type),
            event_id=audit_id(index),
            stream_id="domain",
            previous_event_hash=previous,
        )
        assert record.action.value == event_type.value
        assert record.decision is AuditDecisionResult.RECORD
        replayed = service.append_domain_event(
            _canonical_event(event_type),
            event_id=audit_id(index),
            stream_id="domain",
            previous_event_hash=record.previous_event_hash,
        )
        assert replayed == record
        previous = record.event_hash
    assert len(sink.records) == len(EventType)


def test_governance_decisions_and_hash_chain() -> None:
    sink = InMemoryAuditSink()
    service = AuditService(sink)
    first = service.append_governance(
        event_id=audit_id(30),
        occurred_at=OCCURRED_AT,
        actor_type=ActorType.BUYER,
        actor_id=ActorId("ar_01k2m3n4p5q6r7s8t9v0w1x2k1"),
        action=AuditAction.DISCLOSURE_ALLOW,
        resource_type=AuditResourceType.DISCLOSURE,
        resource_id=RESOURCE_INTENT.to_primitive(),
        resource_version=Version(1),
        decision=AuditDecisionResult.ALLOW,
        reason_codes=(AuditReason.ALLOWED,),
        correlation_id=CORRELATION,
        stream_id="gov",
    )
    second = service.append_governance(
        event_id=audit_id(31),
        occurred_at=OCCURRED_AT,
        actor_type=ActorType.BUYER,
        actor_id=ActorId("ar_01k2m3n4p5q6r7s8t9v0w1x2k1"),
        action=AuditAction.APPROVAL_ALLOW,
        resource_type=AuditResourceType.APPROVAL,
        resource_id="ap_01k2m3n4p5q6r7s8t9v0w1x2f1",
        resource_version=Version(1),
        decision=AuditDecisionResult.ALLOW,
        reason_codes=(AuditReason.ALLOWED,),
        correlation_id=CORRELATION,
        stream_id="gov",
        previous_event_hash=first.event_hash,
    )
    assert second.previous_event_hash == first.event_hash
    with pytest.raises(AuditConflictError):
        service.append_governance(
            event_id=audit_id(32),
            occurred_at=OCCURRED_AT,
            actor_type=ActorType.BUYER,
            actor_id=ActorId("ar_01k2m3n4p5q6r7s8t9v0w1x2k1"),
            action=AuditAction.ISOLATION_DENY,
            resource_type=AuditResourceType.ISOLATION,
            resource_id=INVITATIONS[0].to_primitive(),
            resource_version=Version(1),
            decision=AuditDecisionResult.DENY,
            reason_codes=(AuditReason.PRINCIPAL_MISMATCH,),
            correlation_id=CORRELATION,
            stream_id="gov",
            previous_event_hash=first.event_hash,
        )
    with pytest.raises(AuditConflictError):
        service.append_governance(
            event_id=audit_id(31),
            occurred_at=OCCURRED_AT,
            actor_type=ActorType.BUYER,
            actor_id=ActorId("ar_01k2m3n4p5q6r7s8t9v0w1x2k1"),
            action=AuditAction.APPROVAL_DENY,
            resource_type=AuditResourceType.APPROVAL,
            resource_id="ap_01k2m3n4p5q6r7s8t9v0w1x2f1",
            resource_version=Version(1),
            decision=AuditDecisionResult.DENY,
            reason_codes=(AuditReason.EXPIRED,),
            correlation_id=CORRELATION,
            stream_id="gov",
            previous_event_hash=first.event_hash,
        )
    other = service.append_governance(
        event_id=audit_id(40),
        occurred_at=OCCURRED_AT,
        actor_type=ActorType.BUYER,
        actor_id=ActorId("ar_01k2m3n4p5q6r7s8t9v0w1x2k1"),
        action=AuditAction.IDEMPOTENCY_RESERVE,
        resource_type=AuditResourceType.IDEMPOTENCY,
        resource_id="ik_01k2m3n4p5q6r7s8t9v0w1x2g1",
        resource_version=Version(1),
        decision=AuditDecisionResult.ALLOW,
        reason_codes=(AuditReason.RESERVED,),
        correlation_id=CORRELATION,
        stream_id="other",
    )
    with pytest.raises(AuditConflictError):
        service.append_governance(
            event_id=audit_id(41),
            occurred_at=OCCURRED_AT,
            actor_type=ActorType.BUYER,
            actor_id=ActorId("ar_01k2m3n4p5q6r7s8t9v0w1x2k1"),
            action=AuditAction.IDEMPOTENCY_CONFLICT,
            resource_type=AuditResourceType.IDEMPOTENCY,
            resource_id="ik_01k2m3n4p5q6r7s8t9v0w1x2g1",
            resource_version=Version(1),
            decision=AuditDecisionResult.CONFLICT,
            reason_codes=(AuditReason.REQUEST_MISMATCH,),
            correlation_id=CORRELATION,
            stream_id="other",
            previous_event_hash=first.event_hash,
        )
    assert other.previous_event_hash is None
