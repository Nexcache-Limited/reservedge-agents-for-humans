from itaa_domain import PACKAGE_NAME, PACKAGE_ROLE


def test_domain_smoke() -> None:
    assert PACKAGE_NAME == "itaa-domain"
    assert PACKAGE_ROLE == "cloud-neutral-domain"
