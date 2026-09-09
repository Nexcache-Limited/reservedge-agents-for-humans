from __future__ import annotations

from datetime import UTC, datetime

import pytest

from itaa_application.errors import ApplicationError
from itaa_application.progress_events import (
    ProgressEvent,
    ProgressEventKind,
    validate_progress_fields,
)

OCCURRED = datetime(2026, 8, 20, 16, 0, tzinfo=UTC)
INTENT = "pi_01k2m3n4p5q6r7s8t9v0w1x2y3"
SUPPLIER = "sp_01k2m3n4p5q6r7s8t9v0w1x2b1"


def test_closed_kind_set_is_frozen() -> None:
    assert {item.value for item in ProgressEventKind} == {
        "SOLICITATION_PREPARING",
        "SOLICITATION_DISPATCHED",
        "SUPPLIER_WAITING",
        "SUPPLIER_OFFER_RECEIVED",
        "SUPPLIER_DECLINED",
        "SUPPLIER_TIMED_OUT",
        "SUPPLIER_LATE",
        "SUPPLIER_INVALID",
        "SUPPLIER_FAILED",
        "VALIDATION_COMPLETED",
        "RANKING_COMPLETED",
        "RECOMMENDATION_READY",
        "STREAM_COMPLETED",
    }


def test_supplier_kinds_require_token() -> None:
    with pytest.raises(ApplicationError) as raised:
        validate_progress_fields(
            intent_id=INTENT,
            generation_id="pg_01k2m3n4p5q6r7s8t9v0w1x2g1",
            kind=ProgressEventKind.SUPPLIER_WAITING,
            sequence=1,
            occurred_at=OCCURRED,
            supplier_token=None,
            status=None,
            correlation_id=None,
            terminal=False,
        )
    assert raised.value.field == "supplierToken"


def test_non_supplier_kinds_forbid_token() -> None:
    with pytest.raises(ApplicationError) as raised:
        validate_progress_fields(
            intent_id=INTENT,
            generation_id="pg_01k2m3n4p5q6r7s8t9v0w1x2g1",
            kind=ProgressEventKind.RANKING_COMPLETED,
            sequence=1,
            occurred_at=OCCURRED,
            supplier_token=SUPPLIER,
            status=None,
            correlation_id=None,
            terminal=False,
        )
    assert raised.value.code == "forbidden"


def test_unknown_status_and_terminal_rules() -> None:
    with pytest.raises(ApplicationError):
        validate_progress_fields(
            intent_id=INTENT,
            generation_id="pg_01k2m3n4p5q6r7s8t9v0w1x2g1",
            kind=ProgressEventKind.SUPPLIER_FAILED,
            sequence=1,
            occurred_at=OCCURRED,
            supplier_token=SUPPLIER,
            status="insufficient_capacity",
            correlation_id=None,
            terminal=False,
        )
    with pytest.raises(ApplicationError):
        validate_progress_fields(
            intent_id=INTENT,
            generation_id="pg_01k2m3n4p5q6r7s8t9v0w1x2g1",
            kind=ProgressEventKind.STREAM_COMPLETED,
            sequence=1,
            occurred_at=OCCURRED,
            supplier_token=None,
            status="complete",
            correlation_id=None,
            terminal=False,
        )


def test_generation_id_is_opaque_and_closed() -> None:
    with pytest.raises(ApplicationError) as raised:
        validate_progress_fields(
            intent_id=INTENT,
            generation_id="pg_not-a-valid-generation-id!!",
            kind=ProgressEventKind.SOLICITATION_PREPARING,
            sequence=1,
            occurred_at=OCCURRED,
            supplier_token=None,
            status=None,
            correlation_id=None,
            terminal=False,
        )
    assert raised.value.field == "generationId"
    assert raised.value.code == "schema_invalid"
    with pytest.raises(ApplicationError):
        validate_progress_fields(
            intent_id=INTENT,
            generation_id="ap_01k2m3n4p5q6r7s8t9v0w1x2f1",
            kind=ProgressEventKind.SOLICITATION_PREPARING,
            sequence=1,
            occurred_at=OCCURRED,
            supplier_token=None,
            status=None,
            correlation_id=None,
            terminal=False,
        )


def test_public_payload_uses_only_safe_keys() -> None:
    event = ProgressEvent(
        intent_id=INTENT,
        generation_id="pg_01k2m3n4p5q6r7s8t9v0w1x2g1",
        kind=ProgressEventKind.SUPPLIER_OFFER_RECEIVED,
        sequence=4,
        occurred_at=OCCURRED,
        simulation=True,
        supplier_token=SUPPLIER,
        status=None,
        correlation_id="cr_01k2m3n4p5q6r7s8t9v0w1x2m1",
        terminal=False,
    )
    public = event.to_public()
    assert public["kind"] == "SUPPLIER_OFFER_RECEIVED"
    assert public["generationId"] == "pg_01k2m3n4p5q6r7s8t9v0w1x2g1"
    assert "totalMinor" not in public
    assert "scoreMicros" not in public
    assert public["simulation"] is True
