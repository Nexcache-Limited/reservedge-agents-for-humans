from itaa_ranking import DOMAIN_DEPENDENCY, PACKAGE_NAME, PACKAGE_ROLE, PROFILE_ID, SCORE_SCALE


def test_ranking_smoke() -> None:
    assert PACKAGE_NAME == "itaa-ranking"
    assert PACKAGE_ROLE == "cloud-neutral-ranking"
    assert DOMAIN_DEPENDENCY == "itaa-domain"
    assert PROFILE_ID == "airport_parking_v1"
    assert SCORE_SCALE == 1_000_000
