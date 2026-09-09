from __future__ import annotations

import json
from datetime import UTC, datetime

from itaa_application.local_progress import InMemoryProgressBus
from itaa_application.progress_events import PRIVACY_DENYLIST, ProgressEventKind

OCCURRED = datetime(2026, 8, 20, 16, 0, tzinfo=UTC)
INTENT = "pi_01k2m3n4p5q6r7s8t9v0w1x2y3"
SUPPLIER = "sp_01k2m3n4p5q6r7s8t9v0w1x2b2"


def test_published_events_omit_privacy_denylist() -> None:
    bus = InMemoryProgressBus()
    event = bus.emit(
        intent_id=INTENT,
        kind=ProgressEventKind.SUPPLIER_OFFER_RECEIVED,
        occurred_at=OCCURRED,
        supplier_token=SUPPLIER,
        correlation_id="cr_01k2m3n4p5q6r7s8t9v0w1x2m2",
    )
    blob = json.dumps(event.to_public())
    for needle in (
        "totalMinor",
        "scoreMicros",
        "approvalId",
        "idempotencyKey",
        "buyerToken",
        "prompt",
        "email",
    ):
        assert needle not in blob
    for item in PRIVACY_DENYLIST:
        assert item not in event.to_public()
