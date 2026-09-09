from __future__ import annotations

from datetime import timedelta

import pytest
from fakes import InMemoryIdempotencyRepository
from wp04_helpers import EXPIRES_AT, OCCURRED_AT

from itaa_application.idempotency_service import IdempotencyService
from itaa_domain.identifiers import ActorId, IdempotencyKey
from itaa_policy.errors import PolicyConflictError
from itaa_policy.idempotency import (
    IdempotencyOperation,
    IdempotencyOutcomeKind,
    IdempotencyScope,
    ResultRef,
)

RESULT_REF = ResultRef("rr_01k2m3n4p5q6r7s8t9v0w1x2r1")


def _scope() -> IdempotencyScope:
    return IdempotencyScope(
        actor_id=ActorId("ar_01k2m3n4p5q6r7s8t9v0w1x2k1"),
        operation=IdempotencyOperation.AUTHORIZE_TRANSACTION,
        key=IdempotencyKey("ik_01k2m3n4p5q6r7s8t9v0w1x2g1"),
    )


def test_first_reservation_executes_once_and_replays() -> None:
    service = IdempotencyService(InMemoryIdempotencyRepository())
    calls: list[int] = []

    def effect() -> dict[str, str]:
        calls.append(1)
        return {"status": "ok"}

    first = service.execute(
        scope=_scope(),
        request={"action": "reserve_parking", "amountMinor": 11900},
        occurred_at=OCCURRED_AT,
        expires_at=EXPIRES_AT,
        result_ref=RESULT_REF,
        effect=effect,
    )
    assert first.kind is IdempotencyOutcomeKind.COMPLETED
    pending = service.execute(
        scope=_scope(),
        request={"action": "reserve_parking", "amountMinor": 11900},
        occurred_at=OCCURRED_AT,
        expires_at=EXPIRES_AT,
        result_ref=RESULT_REF,
        effect=effect,
    )
    assert pending.kind is IdempotencyOutcomeKind.REPLAYED
    assert pending.result_ref == first.result_ref == RESULT_REF
    assert calls == [1]


def test_thousand_replays_invoke_effect_once() -> None:
    service = IdempotencyService(InMemoryIdempotencyRepository())
    calls: list[int] = []

    def effect() -> dict[str, str]:
        calls.append(1)
        return {"status": "ok", "id": RESULT_REF.to_primitive()}

    request = {"action": "reserve_parking", "amountMinor": 11900}
    first = service.execute(
        scope=_scope(),
        request=request,
        occurred_at=OCCURRED_AT,
        expires_at=EXPIRES_AT,
        result_ref=RESULT_REF,
        effect=effect,
    )
    for _ in range(1000):
        replayed = service.execute(
            scope=_scope(),
            request=request,
            occurred_at=OCCURRED_AT,
            expires_at=EXPIRES_AT,
            result_ref=RESULT_REF,
            effect=effect,
        )
        assert replayed.kind is IdempotencyOutcomeKind.REPLAYED
        assert replayed.result_ref == first.result_ref
        assert replayed.result_ref == RESULT_REF
        assert replayed.record.response_hash == first.record.response_hash
        assert replayed.record.result_ref == first.record.result_ref
    assert calls == [1]


def test_changed_request_conflicts() -> None:
    service = IdempotencyService(InMemoryIdempotencyRepository())
    service.execute(
        scope=_scope(),
        request={"action": "reserve_parking", "amountMinor": 11900},
        occurred_at=OCCURRED_AT,
        expires_at=EXPIRES_AT,
        result_ref=RESULT_REF,
        effect=lambda: {"status": "ok"},
    )
    with pytest.raises(PolicyConflictError):
        service.execute(
            scope=_scope(),
            request={"action": "reserve_parking", "amountMinor": 11901},
            occurred_at=OCCURRED_AT,
            expires_at=EXPIRES_AT,
            result_ref=RESULT_REF,
            effect=lambda: {"status": "ok"},
        )


def test_pending_duplicate_does_not_execute() -> None:
    repo = InMemoryIdempotencyRepository()
    service = IdempotencyService(repo)
    scope = _scope()
    request = {"action": "reserve_parking"}
    from itaa_policy.idempotency import hash_idempotency_request

    repo.reserve(scope, hash_idempotency_request(request), OCCURRED_AT, EXPIRES_AT)
    calls: list[int] = []
    result = service.execute(
        scope=scope,
        request=request,
        occurred_at=OCCURRED_AT,
        expires_at=EXPIRES_AT,
        result_ref=RESULT_REF,
        effect=lambda: calls.append(1) or {"status": "ok"},
    )
    assert result.kind is IdempotencyOutcomeKind.IN_PROGRESS
    assert calls == []


def test_failed_retry_same_request_executes_once_more() -> None:
    service = IdempotencyService(InMemoryIdempotencyRepository())
    request = {"action": "reserve_parking"}

    def boom() -> dict[str, str]:
        raise RuntimeError("simulated")

    with pytest.raises(RuntimeError):
        service.execute(
            scope=_scope(),
            request=request,
            occurred_at=OCCURRED_AT,
            expires_at=EXPIRES_AT,
            result_ref=RESULT_REF,
            effect=boom,
        )
    calls: list[int] = []
    result = service.execute(
        scope=_scope(),
        request=request,
        occurred_at=OCCURRED_AT,
        expires_at=EXPIRES_AT,
        result_ref=RESULT_REF,
        effect=lambda: calls.append(1) or {"status": "ok"},
    )
    assert result.kind is IdempotencyOutcomeKind.COMPLETED
    assert calls == [1]


def test_expiry_replaces_and_does_not_return_stale_result() -> None:
    service = IdempotencyService(InMemoryIdempotencyRepository())
    service.execute(
        scope=_scope(),
        request={"action": "reserve_parking"},
        occurred_at=OCCURRED_AT,
        expires_at=OCCURRED_AT + timedelta(minutes=5),
        result_ref=RESULT_REF,
        effect=lambda: {"status": "stale"},
    )
    later = OCCURRED_AT + timedelta(minutes=6)
    result = service.execute(
        scope=_scope(),
        request={"action": "reserve_parking", "retry": True},
        occurred_at=later,
        expires_at=later + timedelta(minutes=5),
        result_ref=ResultRef("rr_01k2m3n4p5q6r7s8t9v0w1x2r2"),
        effect=lambda: {"status": "fresh"},
    )
    assert result.kind is IdempotencyOutcomeKind.COMPLETED
    assert result.result_ref == ResultRef("rr_01k2m3n4p5q6r7s8t9v0w1x2r2")


def test_conflicting_completion_is_rejected() -> None:
    repo = InMemoryIdempotencyRepository()
    service = IdempotencyService(repo)
    request = {"action": "reserve_parking"}
    first = service.execute(
        scope=_scope(),
        request=request,
        occurred_at=OCCURRED_AT,
        expires_at=EXPIRES_AT,
        result_ref=RESULT_REF,
        effect=lambda: {"status": "ok"},
    )
    assert first.record.response_hash is not None
    with pytest.raises(PolicyConflictError):
        service.complete_only(
            scope=_scope(),
            request_hash=first.record.request_hash,
            response_hash=first.record.request_hash,
            result_ref=ResultRef("rr_01k2m3n4p5q6r7s8t9v0w1x2r9"),
            occurred_at=OCCURRED_AT,
        )
