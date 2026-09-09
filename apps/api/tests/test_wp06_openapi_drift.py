from __future__ import annotations

from pathlib import Path

from itaa_api.export_openapi import (
    EXPORT_PATH,
    check_openapi,
    main,
    openapi_document,
    write_openapi,
)


def test_openapi_describes_local_simulation_and_matches_export() -> None:
    document = openapi_document()
    dumped = str(document).lower()
    assert document["info"]["version"] == "1.0.0"
    assert "local simulation" in document["info"]["description"].lower()
    assert "production authentication" in document["info"]["description"].lower()
    assert "real reservation" in document["info"]["description"].lower()
    assert "simulated" in dumped
    assert "/healthz" in document["paths"]
    assert "/v1/simulations/airport-parking/intents" in document["paths"]
    assert "/v1/simulations/airport-parking/intents/{intent_id}/events" in document["paths"]
    assert "/v1/agent/sessions" in document["paths"]
    assert check_openapi(EXPORT_PATH) == 0
    assert main(["--check"]) == 0
    assert main([]) == 0


def test_openapi_drift_detects_missing_and_changed_export(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    assert check_openapi(missing) == 1
    write_openapi(missing)
    assert check_openapi(missing) == 0
    missing.write_text("{}\n", encoding="utf-8")
    assert check_openapi(missing) == 1
