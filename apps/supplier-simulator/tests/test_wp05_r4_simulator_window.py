from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest
from test_wp05_simulator_guardrails import _attempts
from test_wp05_solicitation import _collect, _collector
from wp04_helpers import OCCURRED_AT, SUPPLIERS
from wp05_ranking_helpers import rank_golden

from itaa_application.errors import ApplicationError
from itaa_application.supplier_port import ClosedReason, TerminalKind
from itaa_domain.value_objects import JS_SAFE_MAX, parse_utc
from itaa_ranking.vocab import DownsideDimension
from itaa_supplier_simulator.engine import SimulatedSupplier
from itaa_supplier_simulator.harness import seeded_ports
from itaa_supplier_simulator.policy import PARKDIRECT, SKYSHIELD, TERMINALFLEX


def test_clamped_duration_one_microsecond_below_min_declines_without_capacity_change() -> None:
    attempt = replace(
        _attempts()[0],
        deadline=OCCURRED_AT
        + timedelta(seconds=PARKDIRECT.min_validity_seconds)
        - timedelta(microseconds=1),
    )
    supplier = SimulatedSupplier(PARKDIRECT)
    before = supplier.remaining_capacity
    result = supplier.attempt(attempt)
    assert result.kind is TerminalKind.DECLINED
    assert result.reason is ClosedReason.VALIDITY_WINDOW
    assert result.payload is None
    assert supplier.remaining_capacity == before == 12


def test_clamped_duration_one_second_below_min_declines_without_capacity_change() -> None:
    attempt = replace(
        _attempts()[0],
        deadline=OCCURRED_AT + timedelta(seconds=PARKDIRECT.min_validity_seconds - 1),
    )
    supplier = SimulatedSupplier(PARKDIRECT)
    before = supplier.remaining_capacity
    result = supplier.attempt(attempt)
    assert result.kind is TerminalKind.DECLINED
    assert result.reason is ClosedReason.VALIDITY_WINDOW
    assert result.payload is None
    assert supplier.remaining_capacity == before


def test_exact_minimum_duration_offers_and_decrements_capacity_once() -> None:
    attempt = replace(
        _attempts()[0],
        deadline=OCCURRED_AT + timedelta(seconds=PARKDIRECT.min_validity_seconds),
    )
    supplier = SimulatedSupplier(PARKDIRECT)
    before = supplier.remaining_capacity
    result = supplier.attempt(attempt)
    assert result.kind is TerminalKind.OFFER
    assert result.payload is not None
    start = parse_utc(result.payload["validFrom"], "validFrom")
    end = parse_utc(result.payload["validUntil"], "validUntil")
    assert end - start == timedelta(seconds=PARKDIRECT.min_validity_seconds)
    assert supplier.remaining_capacity == before - 1 == 11


def test_normal_jfk_solicitation_still_emits_three_offers() -> None:
    collector, binding, _repo = _collector()
    ports = seeded_ports()
    before = {token: ports[token].remaining_capacity for token in SUPPLIERS}
    result = _collect(collector, binding, ports)
    assert [item.kind for item in result.terminals] == [TerminalKind.OFFER] * 3
    for terminal in result.terminals:
        assert terminal.payload is not None
        assert terminal.payload["simulation"] is True
        start = parse_utc(terminal.payload["validFrom"], "validFrom")
        end = parse_utc(terminal.payload["validUntil"], "validUntil")
        assert end > start
    after = {token: ports[token].remaining_capacity for token in SUPPLIERS}
    assert after == {token: value - 1 for token, value in before.items()}
    assert before == {
        PARKDIRECT.supplier_token: 12,
        SKYSHIELD.supplier_token: 8,
        TERMINALFLEX.supplier_token: 3,
    }


def test_generation_failure_is_buyer_failed_and_leaves_capacity() -> None:
    collector, binding, _repo = _collector()
    ports = seeded_ports()
    broken = SimulatedSupplier(replace(PARKDIRECT, fees_minor=JS_SAFE_MAX))
    before = broken.remaining_capacity
    ports[PARKDIRECT.supplier_token] = broken
    result = _collect(collector, binding, ports)
    kinds = {item.supplier_token: item.kind for item in result.terminals}
    reasons = {item.supplier_token: item.reason for item in result.terminals}
    assert kinds[PARKDIRECT.supplier_token] is TerminalKind.FAILED
    assert reasons[PARKDIRECT.supplier_token] is ClosedReason.FAILED
    assert kinds[SKYSHIELD.supplier_token] is TerminalKind.OFFER
    assert kinds[TERMINALFLEX.supplier_token] is TerminalKind.OFFER
    targeted = next(
        item for item in result.terminals if item.supplier_token == PARKDIRECT.supplier_token
    )
    assert targeted.payload is None
    assert broken.remaining_capacity == before
    assert "alice@" not in str(result)
    with pytest.raises(ApplicationError, match="totalMinor: overflow") as captured:
        SimulatedSupplier(replace(PARKDIRECT, fees_minor=JS_SAFE_MAX)).attempt(_attempts()[0])
    assert "9007199254740991" not in str(captured.value)


def test_seeded_golden_scores_remain_locked() -> None:
    result = rank_golden()
    scores = {item.offer_id.to_primitive(): item.score_micros for item in result.ranked}
    assert scores["of_01k2m3n4p5q6r7s8t9v0w1x2a2"] == 671_000
    assert scores["of_01k2m3n4p5q6r7s8t9v0w1x2a1"] == 660_000
    assert scores["of_01k2m3n4p5q6r7s8t9v0w1x2a3"] == 535_000
    assert result.downside is not None
    assert result.downside.dimension is DownsideDimension.TOTAL_MINOR
    assert result.downside.delta == 2900
