"""Pure CostLedger projection. Integer minor units. No invented FX."""

from __future__ import annotations

from dataclasses import dataclass

from itaa_domain.booking_task_states import BookingTaskState

TRANSACTIONAL_BUCKET_PRECEDENCE: tuple[str, ...] = (
    "confirmedBookingMinor",
    "authorizedLiveMinor",
    "bookingPendingMinor",
    "authorizedSimulatedMinor",
    "selectedNotAuthorizedMinor",
    "estimatedMinor",
)

_ESTIMATED_STATES: frozenset[BookingTaskState] = frozenset(
    {
        BookingTaskState.OFFERS_READY,
        BookingTaskState.RESEARCHING,
        BookingTaskState.OFFERS_EXPIRING,
        BookingTaskState.A1_REVIEW,
        BookingTaskState.A1_BLOCKED,
        BookingTaskState.A2_REQUIRED,
        BookingTaskState.MISSING_DETAILS,
    }
)
_SELECTED_STATES: frozenset[BookingTaskState] = frozenset(
    {
        BookingTaskState.A4_REQUIRED,
        BookingTaskState.A3_REVIEW,
    }
)
_EXPIRED = frozenset({"expired", "superseded"})


@dataclass(frozen=True, slots=True)
class LedgerOfferInput:
    total_minor: int
    tax_minor: int
    fees_minor: int
    currency: str
    validity: str
    recommended: bool = False
    selected: bool = False
    authorized: bool = False


@dataclass(frozen=True, slots=True)
class LedgerTaskInput:
    task_id: str
    state: BookingTaskState
    offers: tuple[LedgerOfferInput, ...]


def project_cost_ledger(
    intent_id: str,
    ledger_id: str,
    tasks: tuple[LedgerTaskInput, ...],
    *,
    simulation: bool = True,
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for task in tasks:
        currencies = sorted({offer.currency for offer in task.offers})
        if not currencies:
            continue
        for currency in currencies:
            rows.append(_row_for(task, currency, simulation=simulation))
    rows.sort(key=lambda row: (str(row["taskId"]), str(row["currency"])))
    codes = sorted({str(row["currency"]) for row in rows})
    return {
        "schemaVersion": "1.0",
        "ledgerId": ledger_id,
        "intentId": intent_id,
        "simulation": True,
        "rows": rows,
        "currencies": codes,
    }


def _row_for(task: LedgerTaskInput, currency: str, *, simulation: bool) -> dict[str, object]:
    scoped = tuple(offer for offer in task.offers if offer.currency == currency)
    selected = next((offer for offer in scoped if offer.selected or offer.authorized), None)
    recommended = next((offer for offer in scoped if offer.recommended), None)
    confirmed = 0
    authorized_live = 0
    booking_pending = 0
    authorized_simulated = 0
    selected_not_authorized = 0
    estimated = 0
    taxes = 0
    source: LedgerOfferInput | None = None
    if task.state is BookingTaskState.CONFIRMED_BOOKING:
        source = selected or recommended
        if source is not None and not simulation:
            confirmed = source.total_minor
    elif task.state is BookingTaskState.AUTHORIZED_LIVE:
        source = selected or recommended
        if source is not None and not simulation:
            authorized_live = source.total_minor
    elif task.state is BookingTaskState.BOOKING_PENDING:
        source = selected or recommended
        if source is not None and not simulation:
            booking_pending = source.total_minor
    elif task.state is BookingTaskState.AUTHORIZED_SIMULATED:
        source = selected or recommended
        if source is not None:
            authorized_simulated = source.total_minor
    elif task.state in _SELECTED_STATES:
        source = selected
        if source is not None:
            selected_not_authorized = source.total_minor
    elif task.state in _ESTIMATED_STATES:
        source = recommended
        if source is not None:
            estimated = source.total_minor
    if source is not None:
        taxes = source.tax_minor + source.fees_minor
    expired_excluded = sum(
        offer.total_minor
        for offer in scoped
        if offer.validity in _EXPIRED and offer is not selected
    )
    return {
        "taskId": task.task_id,
        "currency": currency,
        "confirmedBookingMinor": 0 if simulation else confirmed,
        "authorizedSimulatedMinor": authorized_simulated,
        "authorizedLiveMinor": 0 if simulation else authorized_live,
        "bookingPendingMinor": 0 if simulation else booking_pending,
        "selectedNotAuthorizedMinor": selected_not_authorized,
        "estimatedMinor": estimated,
        "expiredExcludedMinor": expired_excluded,
        "taxesFeesMinor": taxes,
        "depositsHoldsMinor": 0,
        "payableNowMinor": 0,
        "payableLaterMinor": 0,
    }
