"""Canonical golden-path ports isolate demo capacity per roster instance."""

from __future__ import annotations

from itaa_supplier_simulator.canonical import (
    DEMO_CAPACITY,
    CanonicalGoldenSupplier,
    canonical_golden_ports,
)
from itaa_supplier_simulator.policy import SKYSHIELD


def test_canonical_ports_are_isolated_between_calls() -> None:
    first = canonical_golden_ports()
    second = canonical_golden_ports()
    sky = SKYSHIELD.supplier_token
    sky_first = first[sky]
    sky_second = second[sky]
    assert isinstance(sky_first, CanonicalGoldenSupplier)
    assert isinstance(sky_second, CanonicalGoldenSupplier)
    assert sky_first is not sky_second
    assert sky_first.remaining_capacity == DEMO_CAPACITY
    sky_first.restore_capacity(0)
    assert sky_first.remaining_capacity == 0
    assert sky_second.remaining_capacity == DEMO_CAPACITY
