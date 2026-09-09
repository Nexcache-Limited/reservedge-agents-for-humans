from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from itaa_domain.errors import DomainInvariantError
from itaa_domain.identifiers import ActorId, CorrelationId, IntentId, OfferId
from itaa_domain.value_objects import (
    JS_SAFE_MAX,
    ActorRef,
    ActorType,
    AirportCode,
    Money,
    PayloadHash,
    TimeWindow,
    Version,
    format_utc,
    parse_utc,
)

UTC = UTC
HASH = "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"


def test_money_accepts_boundaries_and_serializes() -> None:
    zero = Money(0, "USD")
    max_value = Money(JS_SAFE_MAX, "USD")
    assert zero.to_primitive() == {"amountMinor": 0, "currency": "USD"}
    assert max_value.amount_minor == JS_SAFE_MAX
    assert Money(11900, "USD") == Money(11900, "USD")
    assert Money(11900, "USD") != Money(11900, "EUR")


@pytest.mark.parametrize(
    "amount",
    [-1, JS_SAFE_MAX + 1, 1.5, True, "10"],
)
def test_money_rejects_invalid_amounts(amount: object) -> None:
    with pytest.raises(DomainInvariantError) as exc:
        Money(amount, "USD")  # type: ignore[arg-type]
    assert exc.value.field == "amount_minor"


@pytest.mark.parametrize("currency", ["usd", "US", "USDD", "US1", ""])
def test_money_rejects_invalid_currency(currency: str) -> None:
    with pytest.raises(DomainInvariantError) as exc:
        Money(1, currency)
    assert exc.value.field == "currency"


def test_money_arithmetic_and_ordering_are_same_currency_only() -> None:
    left = Money(100, "USD")
    right = Money(40, "USD")
    other = Money(40, "EUR")
    assert (left + right).amount_minor == 140
    assert (left - right).amount_minor == 60
    assert right < left
    with pytest.raises(DomainInvariantError):
        left + other
    with pytest.raises(DomainInvariantError):
        left - other
    with pytest.raises(DomainInvariantError):
        _ = left < other
    with pytest.raises(DomainInvariantError):
        left - Money(200, "USD")
    with pytest.raises(DomainInvariantError):
        Money(JS_SAFE_MAX, "USD") + Money(1, "USD")


def test_time_window_utc_contains_and_expiry() -> None:
    window = TimeWindow(
        datetime(2026, 8, 20, 16, 0, tzinfo=UTC),
        datetime(2026, 8, 21, 16, 0, tzinfo=UTC),
    )
    inside = datetime(2026, 8, 21, 0, 0, tzinfo=UTC)
    start = window.start
    end = window.end
    assert window.contains(inside)
    assert window.contains(start)
    assert not window.contains(end)
    assert window.is_expired_at(end)
    assert not window.is_expired_at(inside)
    assert window.duration() == timedelta(days=1)
    assert window.to_primitive() == {
        "start": "2026-08-20T16:00:00Z",
        "end": "2026-08-21T16:00:00Z",
    }


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (datetime(2026, 8, 21, 16, 0, tzinfo=UTC), datetime(2026, 8, 20, 16, 0, tzinfo=UTC)),
        (datetime(2026, 8, 20, 16, 0, tzinfo=UTC), datetime(2026, 8, 20, 16, 0, tzinfo=UTC)),
        (datetime(2026, 8, 20, 16, 0), datetime(2026, 8, 21, 16, 0, tzinfo=UTC)),
        (
            datetime(2026, 8, 20, 16, 0, tzinfo=timezone(timedelta(hours=-4))),
            datetime(2026, 8, 21, 16, 0, tzinfo=UTC),
        ),
    ],
)
def test_time_window_rejects_invalid_bounds(start: datetime, end: datetime) -> None:
    with pytest.raises(DomainInvariantError):
        TimeWindow(start, end)


def test_parse_and_format_utc_are_canonical() -> None:
    parsed = parse_utc("2026-08-20T15:00:00.123Z", "created_at")
    assert format_utc(parsed) == "2026-08-20T15:00:00.123Z"
    assert parse_utc("2024-02-29T00:00:00Z", "created_at").day == 29
    with pytest.raises(DomainInvariantError):
        parse_utc("2026-08-20T15:00:00+00:00", "created_at")
    with pytest.raises(DomainInvariantError):
        parse_utc("2025-02-29T00:00:00Z", "created_at")


def test_version_increments_and_rejects_overflow() -> None:
    first = Version.initial()
    assert first.value == 1
    assert first.next().value == 2
    with pytest.raises(DomainInvariantError):
        Version(0)
    with pytest.raises(DomainInvariantError):
        Version(JS_SAFE_MAX).next()
    with pytest.raises(DomainInvariantError):
        Version(True)  # type: ignore[arg-type]


def test_payload_hash_and_airport_boundaries() -> None:
    assert PayloadHash(HASH).to_primitive() == HASH
    assert AirportCode("JFK").to_primitive() == "JFK"
    with pytest.raises(DomainInvariantError):
        PayloadHash("sha256:" + "A" * 64)
    with pytest.raises(DomainInvariantError):
        PayloadHash("sha256:abc")
    with pytest.raises(DomainInvariantError):
        AirportCode("jfk")
    with pytest.raises(DomainInvariantError):
        AirportCode("JF")
    with pytest.raises(DomainInvariantError):
        AirportCode("JFK1")


def test_actor_and_correlation_reject_identity_shaped_values() -> None:
    with pytest.raises(DomainInvariantError) as exc:
        ActorId("alice.smith")
    assert "alice" not in str(exc.value)
    with pytest.raises(DomainInvariantError) as exc:
        CorrelationId("jfk.trip.alice")
    assert "alice" not in str(exc.value)
    with pytest.raises(DomainInvariantError):
        ActorRef(ActorType.BUYER, "alice.smith")  # type: ignore[arg-type]
    actor = ActorRef(ActorType.SYSTEM, ActorId("ar_01k2m3n4p5q6r7s8t9v0w1x2k1"))
    assert actor.to_primitive()["actorType"] == "system"


def test_nine_digit_fractional_timestamps_truncate_to_microseconds() -> None:
    parsed = parse_utc("2026-08-20T15:00:00.123456789Z", "created_at")
    assert format_utc(parsed) == "2026-08-20T15:00:00.123456Z"


def test_typed_ids_are_not_interchangeable() -> None:
    intent = IntentId("pi_01k2m3n4p5q6r7s8t9v0w1x2y3")
    with pytest.raises(DomainInvariantError):
        OfferId(intent.to_primitive())
    with pytest.raises(DomainInvariantError):
        IntentId("pi_01k2m3n4p5q6r7s8t9v0w1x2yI")
    with pytest.raises(DomainInvariantError):
        IntentId("of_01k2m3n4p5q6r7s8t9v0w1x2y3")
