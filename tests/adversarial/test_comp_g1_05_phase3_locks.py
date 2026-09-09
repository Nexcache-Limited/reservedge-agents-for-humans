"""Phase 3 locks: live workspace must not hard-code prototype ranking values."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_phase3_live_workspace_does_not_hard_code_prototype_vector() -> None:
    blob = "".join(
        (ROOT / rel).read_text()
        for rel in (
            "apps/web/src/screens/LiveParkingWorkspace.tsx",
            "apps/web/src/App.tsx",
            "apps/web/src/reservedge/map-snapshot.ts",
        )
    )
    for needle in ("671000", "671,000", "JetPark", "$71.40"):
        assert needle not in blob
