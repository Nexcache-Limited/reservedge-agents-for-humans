from __future__ import annotations

import hashlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "docs" / "source-of-truth"

EXPECTED_SHA256 = {
    "ITAA_v1_Product_and_Technical_Specification.docx": (
        "4fd24641963a19f93fdead7aab3fc38ee5c6a891c5cc31d3246570da21d59900"
    ),
    "ITAA_Engineering_Kickoff_Pack.docx": (
        "611c8f87925a81771870cc0eb1a57a56556845f96d49b828d2109fe1fbef13d4"
    ),
    "ITAA_Unified_UI_UX_Design_Specification.docx": (
        "aeba64e717eb07446a90e95b1f47b633c143000d7138d4abcee0aeee7e955e7f"
    ),
}


def test_normative_documents_match_recorded_checksums() -> None:
    for filename, expected in EXPECTED_SHA256.items():
        path = SOURCE / filename
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == expected, f"{filename} checksum mismatch"
