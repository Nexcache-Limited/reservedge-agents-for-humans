"""Phase 2 locks: registry/composer must not hard-code ranking scores."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_phase2_sources_do_not_hard_code_ranking_vector() -> None:
    blob = "".join(
        (ROOT / rel).read_text()
        for rel in (
            "apps/web/src/reservedge/registry.ts",
            "apps/web/src/reservedge/composer-engine.ts",
            "apps/web/src/screens/Composer.tsx",
            "apps/web/src/screens/DomainPicker.tsx",
        )
    )
    for needle in ("671000", "671,000", "SkyShield", "ParkDirect", "TerminalFlex", "JetPark"):
        assert needle not in blob
