from __future__ import annotations

from pathlib import Path

import pytest

from boundaries import (
    FORBIDDEN_DOMAIN_MODULES,
    scan_application,
    scan_contracts,
    scan_domain,
    scan_observability,
    scan_policy,
    scan_python_file,
    scan_ranking,
    scan_ui_kit,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.mark.security
def test_domain_package_has_no_prohibited_imports() -> None:
    assert scan_domain(REPO_ROOT) == []


@pytest.mark.security
def test_application_package_has_no_provider_imports() -> None:
    assert scan_application(REPO_ROOT) == []


@pytest.mark.security
def test_ranking_package_imports_only_domain_and_stdlib() -> None:
    assert scan_ranking(REPO_ROOT) == []


@pytest.mark.security
def test_policy_package_imports_only_domain_and_stdlib() -> None:
    assert scan_policy(REPO_ROOT) == []


@pytest.mark.security
def test_observability_package_imports_only_domain_and_stdlib() -> None:
    assert scan_observability(REPO_ROOT) == []


@pytest.mark.security
def test_contracts_package_has_no_core_or_provider_imports() -> None:
    assert scan_contracts(REPO_ROOT) == []


@pytest.mark.security
def test_ui_kit_manifest_has_no_product_or_provider_sdks() -> None:
    assert scan_ui_kit(REPO_ROOT) == []


@pytest.mark.security
def test_prohibited_domain_fixture_is_rejected() -> None:
    violations = scan_python_file(
        FIXTURES / "prohibited_domain_import.py",
        FORBIDDEN_DOMAIN_MODULES,
    )
    names = {item.message for item in violations}
    assert "prohibited import 'fastapi'" in names
    assert "prohibited import 'boto3'" in names
    assert "prohibited import 'itaa_application'" in names


@pytest.mark.security
def test_allowed_domain_fixture_is_accepted() -> None:
    violations = scan_python_file(
        FIXTURES / "allowed_domain_import.py",
        FORBIDDEN_DOMAIN_MODULES,
    )
    assert violations == []
