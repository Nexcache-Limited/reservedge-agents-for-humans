from __future__ import annotations

import pytest
from wp04_helpers import CORRELATION, OCCURRED_AT, RESOURCE_INTENT, audit_id

from itaa_domain.events import CLOSED_REASON_CODES
from itaa_domain.identifiers import ActorId, SignatureHandle
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
    IsolationAuditRef,
    record_as_mapping,
)
from itaa_observability.errors import ObservabilityError


def _record(**overrides) -> AuditRecord:
    payload = {
        "event_id": audit_id(90),
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
        "event_hash": PayloadHash("sha256:" + ("b" * 64)),
        "policy_id": POLICY_ID,
        "policy_version": POLICY_VERSION,
        "redaction_profile": REDACTION_PROFILE,
    }
    payload.update(overrides)
    return AuditRecord(**payload)


def test_closed_reasons_cover_domain_and_reject_arbitrary_text() -> None:
    assert {item.value for item in AuditReason} >= CLOSED_REASON_CODES
    identity = "alice@example.com"
    with pytest.raises(ObservabilityError) as captured:
        _record(reason_codes=(identity,))
    assert identity not in str(captured.value)
    with pytest.raises(ObservabilityError, match="incompatible"):
        _record(reason_codes=(AuditReason.PRINCIPAL_MISMATCH,))
    with pytest.raises(ObservabilityError, match="incompatible"):
        _record(decision=AuditDecisionResult.DENY)


@pytest.mark.parametrize(
    "value",
    [
        "alice@example.com",
        "Ada Lovelace",
        {"email": "alice@example.com"},
        "pi_not-an-id",
    ],
)
def test_resource_ids_reject_identity_and_free_text(value: object) -> None:
    with pytest.raises(ObservabilityError) as captured:
        _record(resource_id=value)  # type: ignore[arg-type]
    text = str(captured.value)
    assert "alice@example.com" not in text
    assert "Ada" not in text
    assert "Lovelace" not in text


def test_optional_primitives_use_exact_types() -> None:
    with pytest.raises(ObservabilityError, match="invalid_opaque_syntax"):
        _record(signature_handle="sg_alice@example.com")
    handle = SignatureHandle("sg_01k2m3n4p5q6r7s8t9v0w1x2c1")
    record = _record(signature_handle=handle)
    mapping = record_as_mapping(record)
    assert mapping["signatureHandle"] == handle.to_primitive()
    assert "alice" not in str(mapping)
    with pytest.raises(ObservabilityError, match="must_be_true_or_absent"):
        _record(simulation=False)
    IsolationAuditRef("iv_01k2m3n4p5q6r7s8t9v0w1x2j1")
    with pytest.raises(ObservabilityError, match="invalid_opaque_syntax") as captured:
        IsolationAuditRef("iv_alice@example.com")
    assert "alice@example.com" not in str(captured.value)
