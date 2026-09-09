from itaa_application import (
    CONTRACTS_DEPENDENCY,
    DOMAIN_DEPENDENCY,
    OBSERVABILITY_DEPENDENCY,
    PACKAGE_NAME,
    PACKAGE_ROLE,
    POLICY_DEPENDENCY,
    RANKING_DEPENDENCY,
)


def test_application_smoke() -> None:
    assert PACKAGE_NAME == "itaa-application"
    assert PACKAGE_ROLE == "cloud-neutral-application"
    assert DOMAIN_DEPENDENCY == "itaa-domain"
    assert POLICY_DEPENDENCY == "itaa-policy"
    assert OBSERVABILITY_DEPENDENCY == "itaa-observability"
    assert RANKING_DEPENDENCY == "itaa-ranking"
    assert CONTRACTS_DEPENDENCY == "itaa-contracts-generated"
