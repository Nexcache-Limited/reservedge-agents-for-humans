from itaa_policy import DOMAIN_DEPENDENCY, PACKAGE_NAME, PACKAGE_ROLE


def test_policy_smoke() -> None:
    assert PACKAGE_NAME == "itaa-policy"
    assert PACKAGE_ROLE == "cloud-neutral-policy"
    assert DOMAIN_DEPENDENCY == "itaa-domain"
