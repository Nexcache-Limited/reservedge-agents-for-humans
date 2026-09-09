"""Hash and append redaction-safe audit records."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from itaa_application.governance_ports import ApplicationAuditSink
from itaa_domain.events import DomainEvent
from itaa_domain.identifiers import ActorId, ApprovalId, CorrelationId
from itaa_domain.value_objects import ActorType, PayloadHash, Version
from itaa_observability.audit import (
    AuditAction,
    AuditDecisionResult,
    AuditReason,
    AuditRecord,
    AuditResourceType,
    ProviderLabel,
    audit_hash_material,
    governance_record,
    project_domain_event,
)
from itaa_policy.canonical import SEPARATOR_AUDIT_EVENT, hash_canonical


class AuditService:
    def __init__(self, sink: ApplicationAuditSink) -> None:
        self._sink = sink

    def append_domain_event(
        self,
        event: DomainEvent,
        *,
        event_id: str,
        stream_id: str | None = None,
        previous_event_hash: PayloadHash | None = None,
    ) -> AuditRecord:
        placeholder = PayloadHash("sha256:" + ("0" * 64))
        draft = project_domain_event(
            event,
            event_id=event_id,
            event_hash=placeholder,
            previous_event_hash=previous_event_hash,
        )
        digest = hash_canonical(SEPARATOR_AUDIT_EVENT, audit_hash_material(draft))
        return self._sink.append(replace(draft, event_hash=digest), stream_id=stream_id)

    def append_governance(
        self,
        *,
        event_id: str,
        occurred_at: datetime,
        actor_type: ActorType,
        actor_id: ActorId,
        action: AuditAction,
        resource_type: AuditResourceType,
        resource_id: str,
        resource_version: Version,
        decision: AuditDecisionResult,
        reason_codes: tuple[AuditReason, ...],
        correlation_id: CorrelationId,
        payload_hash: PayloadHash | None = None,
        approval_id: ApprovalId | None = None,
        simulation: bool | None = None,
        stream_id: str | None = None,
        previous_event_hash: PayloadHash | None = None,
        provider_label: ProviderLabel | None = None,
    ) -> AuditRecord:
        placeholder = PayloadHash("sha256:" + ("0" * 64))
        draft = governance_record(
            event_id=event_id,
            occurred_at=occurred_at,
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_version=resource_version,
            decision=decision,
            reason_codes=reason_codes,
            correlation_id=correlation_id,
            event_hash=placeholder,
            payload_hash=payload_hash,
            approval_id=approval_id,
            simulation=simulation,
            previous_event_hash=previous_event_hash,
            provider_label=provider_label,
        )
        digest = hash_canonical(SEPARATOR_AUDIT_EVENT, audit_hash_material(draft))
        return self._sink.append(replace(draft, event_hash=digest), stream_id=stream_id)
