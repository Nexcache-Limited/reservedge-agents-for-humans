from __future__ import annotations

from itaa_validate_contracts.cli import main
from itaa_validate_contracts.schema import DOCUMENT_KEYS, PHASE1_DOCUMENT_KEYS, load_registry


def test_registry_lists_all_document_schemas() -> None:
    keys = {
        entry.path.replace("schemas/v1/", "").replace(".schema.json", "")
        for entry in load_registry()
        if entry.kind == "document"
    }
    allowed = set(DOCUMENT_KEYS) | set(PHASE1_DOCUMENT_KEYS)
    assert set(DOCUMENT_KEYS) <= keys
    assert keys <= allowed


def test_cli_passes_without_drift_on_canonical_contracts() -> None:
    assert main(["--skip-drift"]) == 0
