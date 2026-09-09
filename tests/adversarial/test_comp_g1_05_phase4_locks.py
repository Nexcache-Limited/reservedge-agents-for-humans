"""Phase 4 locks: competition UI must not hard-code prototype or ranking literals."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

COMPETITION_SURFACES = (
    "apps/web/src/screens/LiveParkingWorkspace.tsx",
    "apps/web/src/reservedge/competition-offers.tsx",
    "apps/web/src/App.tsx",
    "apps/web/src/reservedge/map-snapshot.ts",
)


def test_phase4_competition_path_does_not_hard_code_prototype_or_scores() -> None:
    blob = "".join((ROOT / rel).read_text() for rel in COMPETITION_SURFACES)
    for needle in ("JetPark", "$71.40", "671000", "660000", "535000"):
        assert needle not in blob


def test_phase4_competition_path_names_locked_suppliers_from_catalog_only() -> None:
    offers = (ROOT / "apps/web/src/reservedge/competition-offers.tsx").read_text()
    assert "SkyShield" in offers
    assert "ParkDirect" in offers
    assert "TerminalFlex" in offers
    assert "671,000" not in offers
    assert "USD 29.00" not in offers
