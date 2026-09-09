"""Isolated deterministic simulated suppliers. Availability is simulated only."""

from __future__ import annotations

from itaa_supplier_simulator.canonical import (
    CanonicalTrustedSpec,
    canonical_golden_ports,
    canonical_trusted_specs,
)
from itaa_supplier_simulator.harness import seeded_ports
from itaa_supplier_simulator.policy import PARKDIRECT, SKYSHIELD, TERMINALFLEX

PACKAGE_NAME = "itaa-supplier-simulator"
PACKAGE_ROLE = "isolated-simulated-suppliers"
SIMULATION = True

__all__ = [
    "PACKAGE_NAME",
    "PACKAGE_ROLE",
    "PARKDIRECT",
    "SIMULATION",
    "SKYSHIELD",
    "TERMINALFLEX",
    "CanonicalTrustedSpec",
    "canonical_golden_ports",
    "canonical_trusted_specs",
    "seeded_ports",
]
