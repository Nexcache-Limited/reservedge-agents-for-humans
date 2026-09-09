from __future__ import annotations

import pytest
from test_approvals import _a2
from wp04_helpers import (
    A1_ID,
    A2_ID,
    CORRELATION,
    EXPIRES_AT,
    OCCURRED_AT,
    REVOKE_ID,
    SUPPLIERS,
    audit_id,
)
from wp05_helpers import load_offer
from wp06_fakes import (
    FailingOfferPort,
    FixtureOfferPort,
    FixtureRoster,
    accept_command,
    authorize_command,
    build_facade,
    governance,
    intent_id,
    jfk_payload,
)

from itaa_application.audit_service import AuditService
from itaa_application.errors import ApplicationError
from itaa_application.local_memory import (
    InMemoryApprovalRepository,
    InMemoryAuditSink,
    InMemoryIdempotencyRepository,
)
from itaa_application.session_models import BuyerSessionState
from itaa_domain.identifiers import ActorId, ApprovalId, IdempotencyKey
from itaa_domain.value_objects import ActorType, PayloadHash, Version
from itaa_observability.audit import (
    AuditAction,
    AuditDecisionResult,
    AuditReason,
    AuditResourceType,
)
from itaa_observability.errors import AuditConflictError
from itaa_policy.approvals import ApprovalRevocation
from itaa_policy.errors import PolicyConflictError, PolicyError
from itaa_policy.idempotency import IdempotencyOperation, IdempotencyScope, ResultRef


def test_rejected_confirm_leaves_snapshot_unchanged() -> None:
    facade = build_facade()
    created = facade.create_purchase_intent(jfk_payload())
    with pytest.raises(ApplicationError):
        facade.confirm_requirement(intent_id(), governance("not-an-approval"))
    assert facade.get_buyer_snapshot(intent_id()).to_primitive() == created.to_primitive()


def test_live_mode_fails_before_mutation() -> None:
    facade = build_facade()
    facade.create_purchase_intent(jfk_payload())
    facade.confirm_requirement(intent_id(), governance(A1_ID))
    dispatched = facade.approve_and_dispatch(intent_id(), governance(A2_ID))
    accepted = facade.accept_recommended_or_selected_offer(
        intent_id(), accept_command(dispatched.recommended_offer_id or "")
    )
    winner = next(item for item in dispatched.offers if item.recommended)
    before = facade.get_buyer_snapshot(intent_id())
    with pytest.raises(ApplicationError, match="mode: mode_forbidden"):
        facade.authorize_simulated_transaction(
            intent_id(),
            authorize_command(
                acceptance_id=accepted.acceptance.acceptance_id if accepted.acceptance else "",
                amount_minor=winner.total_minor,
                supplier_token=winner.supplier_token,
                mode="LIVE",
            ),
        )
    after = facade.get_buyer_snapshot(intent_id())
    assert after.to_primitive() == before.to_primitive()
    assert after.state is BuyerSessionState.ACCEPTANCE_RECORDED


def test_conflicting_idempotency_does_not_mutate() -> None:
    facade = build_facade()
    facade.create_purchase_intent(jfk_payload())
    facade.confirm_requirement(intent_id(), governance(A1_ID))
    dispatched = facade.approve_and_dispatch(intent_id(), governance(A2_ID))
    accepted = facade.accept_recommended_or_selected_offer(
        intent_id(), accept_command(dispatched.recommended_offer_id or "")
    )
    winner = next(item for item in dispatched.offers if item.recommended)
    assert accepted.acceptance is not None
    first = facade.authorize_simulated_transaction(
        intent_id(),
        authorize_command(
            acceptance_id=accepted.acceptance.acceptance_id,
            amount_minor=winner.total_minor,
            supplier_token=winner.supplier_token,
        ),
    )
    with pytest.raises(ApplicationError, match="idempotency_key: request_mismatch"):
        facade.authorize_simulated_transaction(
            intent_id(),
            authorize_command(
                acceptance_id=accepted.acceptance.acceptance_id,
                amount_minor=winner.total_minor + 1,
                supplier_token=winner.supplier_token,
            ),
        )
    assert facade.get_buyer_snapshot(intent_id()).to_primitive() == first.to_primitive()


def test_isolated_supplier_failure_still_ranks_others() -> None:
    ports = {
        SUPPLIERS[0]: FixtureOfferPort(load_offer("offer-parkdirect.json")),
        SUPPLIERS[1]: FailingOfferPort(),
        SUPPLIERS[2]: FixtureOfferPort(load_offer("offer-terminalflex.json")),
    }
    facade = build_facade(roster=FixtureRoster(ports))
    facade.create_purchase_intent(jfk_payload())
    facade.confirm_requirement(intent_id(), governance(A1_ID))
    snapshot = facade.approve_and_dispatch(intent_id(), governance(A2_ID))
    kinds = {item.supplier_token: item.kind for item in snapshot.supplier_outcomes}
    assert kinds[SUPPLIERS[1].to_primitive()] == "FAILED"
    assert len(snapshot.offers) == 2


def test_local_memory_adapters_reject_conflicts_without_leaking() -> None:
    approvals = InMemoryApprovalRepository()
    grant = _a2()
    assert approvals.append(grant) == grant
    assert approvals.append(grant) == grant
    with pytest.raises(PolicyConflictError):
        approvals.append(_a2(count=2))
    assert approvals.get(A2_ID) == grant
    missing = ApprovalId("ap_01k2m3n4p5q6r7s8t9v0w1x2f8")
    with pytest.raises(PolicyError, match="missing"):
        approvals.revoke(
            ApprovalRevocation(
                revocation_id=REVOKE_ID,
                target_id=missing,
                occurred_at=OCCURRED_AT,
                correlation_id=CORRELATION,
            )
        )
    first = approvals.revoke(
        ApprovalRevocation(
            revocation_id=REVOKE_ID,
            target_id=A2_ID,
            occurred_at=OCCURRED_AT,
            correlation_id=CORRELATION,
        )
    )
    assert approvals.revoke(first) == first
    with pytest.raises(PolicyConflictError, match="already_revoked"):
        approvals.revoke(
            ApprovalRevocation(
                revocation_id=A1_ID,
                target_id=A2_ID,
                occurred_at=OCCURRED_AT,
                correlation_id=CORRELATION,
            )
        )
    assert approvals.is_revoked(A2_ID)
    assert approvals.resolve(A2_ID).revoked is True

    keys = InMemoryIdempotencyRepository()
    scope = IdempotencyScope(
        actor_id=ActorId("ar_01k2m3n4p5q6r7s8t9v0w1x2k1"),
        operation=IdempotencyOperation.AUTHORIZE_TRANSACTION,
        key=IdempotencyKey("ik_01k2m3n4p5q6r7s8t9v0w1x2g1"),
    )
    request = PayloadHash("sha256:" + ("1" * 64))
    other = PayloadHash("sha256:" + ("2" * 64))
    keys.reserve(scope, request, OCCURRED_AT, EXPIRES_AT)
    kind, _record = keys.reserve(scope, other, OCCURRED_AT, EXPIRES_AT)
    assert kind.value == "conflict"
    keys.fail(scope, request, OCCURRED_AT)
    with pytest.raises(PolicyConflictError):
        keys.complete(
            scope,
            request,
            other,
            ResultRef("rr_01k2m3n4p5q6r7s8t9v0w1x2n1"),
            OCCURRED_AT,
        )

    sink = InMemoryAuditSink()
    service = AuditService(sink)
    first_record = service.append_governance(
        event_id=audit_id(1),
        occurred_at=OCCURRED_AT,
        actor_type=ActorType.BUYER,
        actor_id=ActorId("ar_01k2m3n4p5q6r7s8t9v0w1x2k1"),
        action=AuditAction.APPROVAL_ALLOW,
        resource_type=AuditResourceType.APPROVAL,
        resource_id=A2_ID.to_primitive(),
        resource_version=Version.initial(),
        decision=AuditDecisionResult.ALLOW,
        reason_codes=(AuditReason.ALLOWED,),
        correlation_id=CORRELATION,
        stream_id="gov",
    )
    assert sink.append(first_record, stream_id="gov") == first_record
    with pytest.raises(AuditConflictError):
        service.append_governance(
            event_id=audit_id(1),
            occurred_at=OCCURRED_AT,
            actor_type=ActorType.BUYER,
            actor_id=ActorId("ar_01k2m3n4p5q6r7s8t9v0w1x2k1"),
            action=AuditAction.APPROVAL_ALLOW,
            resource_type=AuditResourceType.APPROVAL,
            resource_id=A1_ID.to_primitive(),
            resource_version=Version.initial(),
            decision=AuditDecisionResult.ALLOW,
            reason_codes=(AuditReason.ALLOWED,),
            correlation_id=CORRELATION,
            stream_id="gov",
        )
    assert sink.tail_hash("gov") == first_record.event_hash
