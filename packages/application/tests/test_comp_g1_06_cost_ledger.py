from __future__ import annotations

from itaa_application.cost_ledger_projection import (
    TRANSACTIONAL_BUCKET_PRECEDENCE,
    LedgerOfferInput,
    LedgerTaskInput,
    project_cost_ledger,
)
from itaa_domain.booking_task_states import BookingTaskState

INTENT = "oi_01k2m3n4p5q6r7s8t9v0w1x2y3"
LEDGER = "ld_01k2m3n4p5q6r7s8t9v0w1x2y3"
TASK_A = "bt_01k2m3n4p5q6r7s8t9v0w1x2y3"
TASK_B = "bt_01k2m3n4p5q6r7s8t9v0w1x2y4"

USD_SELECTED = LedgerOfferInput(
    total_minor=14800,
    tax_minor=800,
    fees_minor=400,
    currency="USD",
    validity="valid",
    recommended=True,
    selected=True,
    authorized=True,
)
USD_EXPIRED = LedgerOfferInput(
    total_minor=2100,
    tax_minor=100,
    fees_minor=50,
    currency="USD",
    validity="expired",
)
GBP_ESTIMATE = LedgerOfferInput(
    total_minor=8900,
    tax_minor=400,
    fees_minor=200,
    currency="GBP",
    validity="valid",
    recommended=True,
)


def test_transactional_bucket_precedence_order() -> None:
    assert TRANSACTIONAL_BUCKET_PRECEDENCE == (
        "confirmedBookingMinor",
        "authorizedLiveMinor",
        "bookingPendingMinor",
        "authorizedSimulatedMinor",
        "selectedNotAuthorizedMinor",
        "estimatedMinor",
    )


def test_a4_writes_authorized_simulated_never_confirmed_booking() -> None:
    document = project_cost_ledger(
        INTENT,
        LEDGER,
        (
            LedgerTaskInput(
                TASK_A,
                BookingTaskState.AUTHORIZED_SIMULATED,
                (USD_SELECTED, USD_EXPIRED),
            ),
        ),
        simulation=True,
    )
    row = document["rows"][0]
    assert row["authorizedSimulatedMinor"] == 14800
    assert row["confirmedBookingMinor"] == 0
    assert row["authorizedLiveMinor"] == 0
    assert row["bookingPendingMinor"] == 0
    assert row["selectedNotAuthorizedMinor"] == 0
    assert row["estimatedMinor"] == 0
    assert row["expiredExcludedMinor"] == 2100
    assert row["taxesFeesMinor"] == 1200
    assert row["depositsHoldsMinor"] == 0
    assert row["payableNowMinor"] == 0
    assert row["payableLaterMinor"] == 0
    assert document["simulation"] is True
    assert "fx" not in document
    assert "totalMinor" not in document
    assert "combinedMinor" not in document
    assert "convertedTotalMinor" not in document
    assert "grandTotalMinor" not in document
    assert "scoreMicros" not in document


def test_selected_not_authorized_and_estimated_buckets() -> None:
    selected = project_cost_ledger(
        INTENT,
        LEDGER,
        (
            LedgerTaskInput(
                TASK_A,
                BookingTaskState.A4_REQUIRED,
                (USD_SELECTED, USD_EXPIRED),
            ),
        ),
    )
    assert selected["rows"][0]["selectedNotAuthorizedMinor"] == 14800
    assert selected["rows"][0]["authorizedSimulatedMinor"] == 0
    estimated = project_cost_ledger(
        INTENT,
        LEDGER,
        (
            LedgerTaskInput(
                TASK_A,
                BookingTaskState.OFFERS_READY,
                (USD_SELECTED, USD_EXPIRED),
            ),
        ),
    )
    assert estimated["rows"][0]["estimatedMinor"] == 14800
    assert estimated["rows"][0]["selectedNotAuthorizedMinor"] == 0
    assert estimated["rows"][0]["expiredExcludedMinor"] == 2100


def test_simulation_zeros_live_buckets_even_for_live_states() -> None:
    document = project_cost_ledger(
        INTENT,
        LEDGER,
        (LedgerTaskInput(TASK_A, BookingTaskState.CONFIRMED_BOOKING, (USD_SELECTED,)),),
        simulation=True,
    )
    assert document["rows"][0]["confirmedBookingMinor"] == 0
    live = project_cost_ledger(
        INTENT,
        LEDGER,
        (LedgerTaskInput(TASK_A, BookingTaskState.CONFIRMED_BOOKING, (USD_SELECTED,)),),
        simulation=False,
    )
    assert live["rows"][0]["confirmedBookingMinor"] == 14800


def test_mixed_currencies_stay_separate_without_fx() -> None:
    document = project_cost_ledger(
        INTENT,
        LEDGER,
        (
            LedgerTaskInput(
                TASK_B,
                BookingTaskState.OFFERS_READY,
                (GBP_ESTIMATE,),
            ),
            LedgerTaskInput(
                TASK_A,
                BookingTaskState.AUTHORIZED_SIMULATED,
                (USD_SELECTED, USD_EXPIRED),
            ),
        ),
    )
    rows = document["rows"]
    assert [row["taskId"] for row in rows] == [TASK_A, TASK_B]
    assert [row["currency"] for row in rows] == ["USD", "GBP"]
    assert document["currencies"] == ["GBP", "USD"]
    assert "fx" not in document
    assert rows[0]["authorizedSimulatedMinor"] == 14800
    assert rows[1]["estimatedMinor"] == 8900


def test_offer_shuffle_does_not_change_totals_or_row_order() -> None:
    first = project_cost_ledger(
        INTENT,
        LEDGER,
        (
            LedgerTaskInput(TASK_A, BookingTaskState.OFFERS_READY, (USD_EXPIRED, USD_SELECTED)),
            LedgerTaskInput(TASK_B, BookingTaskState.OFFERS_READY, (GBP_ESTIMATE,)),
        ),
    )
    second = project_cost_ledger(
        INTENT,
        LEDGER,
        (
            LedgerTaskInput(TASK_B, BookingTaskState.OFFERS_READY, (GBP_ESTIMATE,)),
            LedgerTaskInput(TASK_A, BookingTaskState.OFFERS_READY, (USD_SELECTED, USD_EXPIRED)),
        ),
    )
    assert first == second
    assert first["rows"][0]["taskId"] == TASK_A
    assert first["rows"][1]["taskId"] == TASK_B


def test_sibling_rows_are_isolated() -> None:
    tasks = (
        LedgerTaskInput(TASK_A, BookingTaskState.AUTHORIZED_SIMULATED, (USD_SELECTED,)),
        LedgerTaskInput(TASK_B, BookingTaskState.OFFERS_READY, (GBP_ESTIMATE,)),
    )
    before = project_cost_ledger(INTENT, LEDGER, tasks)
    mutated = (
        LedgerTaskInput(
            TASK_A,
            BookingTaskState.A4_REQUIRED,
            (LedgerOfferInput(1, 0, 0, "USD", "valid", selected=True),),
        ),
        tasks[1],
    )
    after = project_cost_ledger(INTENT, LEDGER, mutated)
    assert after["rows"][1] == before["rows"][1]
    assert after["rows"][0]["authorizedSimulatedMinor"] == 0
    assert after["rows"][0]["selectedNotAuthorizedMinor"] == 1
