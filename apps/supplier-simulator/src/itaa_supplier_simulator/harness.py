"""Local composition of three isolated simulated suppliers. Not a live market."""

from __future__ import annotations

from itaa_domain.identifiers import SupplierToken
from itaa_supplier_simulator.engine import SimulatedSupplier
from itaa_supplier_simulator.policy import PARKDIRECT, SKYSHIELD, TERMINALFLEX


def seeded_ports() -> dict[SupplierToken, SimulatedSupplier]:
    return {
        PARKDIRECT.supplier_token: SimulatedSupplier(PARKDIRECT),
        SKYSHIELD.supplier_token: SimulatedSupplier(SKYSHIELD),
        TERMINALFLEX.supplier_token: SimulatedSupplier(TERMINALFLEX),
    }
