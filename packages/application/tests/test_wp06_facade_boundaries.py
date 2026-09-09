from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from boundaries import FORBIDDEN_APPLICATION_MODULES, scan_python_file
from itaa_application.errors import ApplicationError
from itaa_application.golden_path import (
    GoldenPathFacade,
    default_clock,
    http_status_for,
    map_closed_error,
)
from itaa_domain.errors import (
    DomainInvariantError,
    DuplicateActionError,
    ExpiredResourceError,
    InvalidTransitionError,
    OfferVersionMismatchError,
    VersionConflictError,
)
from itaa_policy.errors import PolicyConflictError, PolicyError


def test_golden_path_module_does_not_import_fastapi_or_simulator() -> None:
    path = Path(__file__).resolve().parents[1] / "src" / "itaa_application" / "golden_path.py"
    violations = scan_python_file(path, FORBIDDEN_APPLICATION_MODULES)
    assert violations == []


def test_closed_error_mapping_hides_internal_detail() -> None:
    mapped = map_closed_error(RuntimeError("secret token abc"))
    assert mapped.field == "internal"
    assert mapped.code == "closed"
    assert "abc" not in str(mapped)
    assert http_status_for(ApplicationError("intentId", "unknown_resource")) == 404
    assert http_status_for(ApplicationError("state", "illegal_state")) == 409
    assert http_status_for(ApplicationError("mode", "mode_forbidden")) == 422
    assert http_status_for(ApplicationError("payload", "schema_invalid")) == 400
    assert http_status_for(ApplicationError("idempotencyKey", "mismatch")) == 400
    assert http_status_for(ApplicationError("internal", "injected_fault")) == 500
    assert http_status_for(ApplicationError("internal", "closed")) == 500
    assert map_closed_error(PolicyError("approval_id", "missing")).code == "missing"
    assert map_closed_error(PolicyConflictError("approval_id", "conflict")).code == "conflict"
    assert (
        map_closed_error(InvalidTransitionError("pi", "id", "DRAFT", "dispatch", ())).code
        == "illegal_state"
    )
    assert (
        map_closed_error(DuplicateActionError("pi", "id", "confirm", "CONFIRMED")).code
        == "illegal_state"
    )
    assert (
        map_closed_error(ExpiredResourceError("pi", "id", "2026-08-22T15:00:00Z")).code == "expired"
    )
    assert map_closed_error(OfferVersionMismatchError("of_x", 1, 2)).code == "stale_version"
    assert map_closed_error(VersionConflictError("pi", "id", 1, 2)).code == "illegal_state"
    assert map_closed_error(DomainInvariantError("intent_id", "invalid_opaque_syntax")).field == (
        "intent_id"
    )
    assert default_clock(datetime(2026, 8, 20, 16, 0, tzinfo=UTC)).now().year == 2026
    assert GoldenPathFacade.__module__ == "itaa_application.golden_path"
