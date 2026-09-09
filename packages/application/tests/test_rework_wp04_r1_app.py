from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from fakes import InMemoryApprovalRepository, InMemoryAuditSink
from test_rework_wp04_r1 import _a2_for, _binding
from wp04_helpers import (
    A2_ID,
    BUYER,
    CORRELATION,
    INVITATIONS,
    OCCURRED_AT,
    OWNER,
    RESOURCE_INTENT,
    REVOKE_ID,
    SUPPLIERS,
    audit_id,
)

from itaa_application.approval_service import ApprovalService
from itaa_application.audit_service import AuditService
from itaa_application.dispatch_service import DispatchService
from itaa_domain.identifiers import ActorId
from itaa_domain.value_objects import ActorType, PayloadHash, Version
from itaa_observability.audit import (
    POLICY_ID,
    POLICY_VERSION,
    REDACTION_PROFILE,
    AuditAction,
    AuditDecisionResult,
    AuditReason,
    AuditRecord,
    AuditResourceType,
    record_as_mapping,
)
from itaa_observability.errors import AuditConflictError, ObservabilityError
from itaa_policy.approvals import ApprovalDenyReason, ApprovalRevocation
from itaa_policy.disclosure import DisclosurePurpose
from itaa_policy.envelopes import verify_dispatch
from itaa_policy.errors import PolicyError
from itaa_policy.idempotency import ResultRef


def _governance(**overrides):
    payload = {
        "event_id": audit_id(50),
        "occurred_at": OCCURRED_AT,
        "actor_type": ActorType.BUYER,
        "actor_id": ActorId("ar_01k2m3n4p5q6r7s8t9v0w1x2k1"),
        "action": AuditAction.DISCLOSURE_ALLOW,
        "resource_type": AuditResourceType.DISCLOSURE,
        "resource_id": RESOURCE_INTENT.to_primitive(),
        "resource_version": Version(1),
        "decision": AuditDecisionResult.ALLOW,
        "reason_codes": (AuditReason.ALLOWED,),
        "correlation_id": CORRELATION,
        "event_hash": PayloadHash("sha256:" + ("a" * 64)),
        "policy_id": POLICY_ID,
        "policy_version": POLICY_VERSION,
        "redaction_profile": REDACTION_PROFILE,
    }
    payload.update(overrides)
    return AuditRecord(**payload)


def test_dispatch_service_requires_unrevoked_a2() -> None:
    repo = InMemoryApprovalRepository()
    approvals = ApprovalService(repo)
    dispatch = DispatchService(repo)
    binding = _binding()
    grant = _a2_for(binding)
    approvals.issue(grant)
    allowed = dispatch.authorize(
        A2_ID,
        binding=binding,
        supplier_token=SUPPLIERS[0],
        occurred_at=OCCURRED_AT,
        actor=BUYER,
        owner_id=OWNER,
    )
    assert allowed.allowed is True
    assert allowed.envelope is not None
    membership = verify_dispatch(
        binding,
        supplier_token=SUPPLIERS[0],
        purpose=DisclosurePurpose.PURCHASE_INTENT_DISPATCH,
        intent_resource_version=binding.manifest.intent_resource_version,
        occurred_at=OCCURRED_AT,
    )
    assert membership.envelope_hash == allowed.envelope.envelope_hash
    approvals.revoke(
        ApprovalRevocation(
            revocation_id=REVOKE_ID,
            target_id=A2_ID,
            occurred_at=OCCURRED_AT,
            correlation_id=CORRELATION,
        )
    )
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
    missing = dispatch.authorize(
        None,
        binding=binding,
        supplier_token=SUPPLIERS[0],
        occurred_at=OCCURRED_AT,
        actor=BUYER,
        owner_id=OWNER,
    )
    assert missing.decision.reason is ApprovalDenyReason.MISSING
    assert missing.envelope is None


def test_stream_omission_after_first_event_is_rejected() -> None:
    sink = InMemoryAuditSink()
    service = AuditService(sink)
    first = service.append_governance(
        event_id=audit_id(60),
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
        stream_id="chain",
    )
    with pytest.raises(AuditConflictError, match="chain_mismatch"):
        service.append_governance(
            event_id=audit_id(61),
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
            stream_id="chain",
        )
    with pytest.raises(AuditConflictError, match="chain_mismatch"):
        sink.append(
            _governance(event_id=audit_id(62), previous_event_hash=None),
            stream_id="chain",
        )
    second = service.append_governance(
        event_id=audit_id(63),
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
        stream_id="chain",
        previous_event_hash=first.event_hash,
    )
    replayed = sink.append(second, stream_id="chain")
    assert replayed == second
    assert sink.tail_hash("chain") == second.event_hash
    unchained = service.append_governance(
        event_id=audit_id(64),
        occurred_at=OCCURRED_AT,
        actor_type=ActorType.BUYER,
        actor_id=ActorId("ar_01k2m3n4p5q6r7s8t9v0w1x2k1"),
        action=AuditAction.ISOLATION_ALLOW,
        resource_type=AuditResourceType.ISOLATION,
        resource_id=INVITATIONS[0].to_primitive(),
        resource_version=Version(1),
        decision=AuditDecisionResult.ALLOW,
        reason_codes=(AuditReason.ALLOWED,),
        correlation_id=CORRELATION,
    )
    assert unchained.previous_event_hash is None


def test_wrong_and_cross_stream_predecessors_conflict() -> None:
    sink = InMemoryAuditSink()
    service = AuditService(sink)
    first = service.append_governance(
        event_id=audit_id(70),
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
        stream_id="alpha",
    )
    other = service.append_governance(
        event_id=audit_id(71),
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
        stream_id="beta",
    )
    with pytest.raises(AuditConflictError, match="chain_mismatch"):
        service.append_governance(
            event_id=audit_id(72),
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
            stream_id="alpha",
            previous_event_hash=other.event_hash,
        )
    with pytest.raises(AuditConflictError, match="stream_empty"):
        service.append_governance(
            event_id=audit_id(73),
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
            stream_id="gamma",
            previous_event_hash=first.event_hash,
        )


def test_concurrent_stream_appends_are_atomic() -> None:
    sink = InMemoryAuditSink()
    first = sink.append(_governance(event_id=audit_id(80)), stream_id="race")

    def append_omit() -> str:
        try:
            sink.append(_governance(event_id=audit_id(81)), stream_id="race")
            return "ok"
        except AuditConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: append_omit(), range(8)))
    assert results.count("ok") == 0
    assert results.count("conflict") == 8
    chained = sink.append(
        _governance(event_id=audit_id(82), previous_event_hash=first.event_hash),
        stream_id="race",
    )
    assert sink.tail_hash("race") == chained.event_hash


def test_audit_identity_text_cannot_enter_records_or_errors() -> None:
    identity = "alice@example.com"
    with pytest.raises(ObservabilityError) as resource_error:
        _governance(resource_id=identity)
    with pytest.raises(ObservabilityError) as reason_error:
        _governance(reason_codes=(identity,))
    with pytest.raises(ObservabilityError) as handle_error:
        _governance(signature_handle=identity)
    for captured in (resource_error, reason_error, handle_error):
        text = str(captured.value)
        assert identity not in text
        assert "Alice" not in text
    record = _governance()
    mapping = record_as_mapping(record)
    blob = str(mapping) + record.event_hash.to_primitive()
    assert identity not in blob
    assert "allowed" in mapping["reasonCodes"]


def test_result_ref_identity_is_rejected_without_echo() -> None:
    with pytest.raises(PolicyError) as captured:
        ResultRef("rr_alice@example.com")
    assert "alice@example.com" not in str(captured.value)
