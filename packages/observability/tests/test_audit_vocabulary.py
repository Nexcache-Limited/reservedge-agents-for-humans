from itaa_domain.events import EventType
from itaa_observability import DOMAIN_DEPENDENCY, PACKAGE_NAME, PACKAGE_ROLE
from itaa_observability.audit import AuditAction


def test_observability_smoke() -> None:
    assert PACKAGE_NAME == "itaa-observability"
    assert PACKAGE_ROLE == "cloud-neutral-observability"
    assert DOMAIN_DEPENDENCY == "itaa-domain"
    domain_actions = {item.value for item in EventType}
    assert domain_actions <= {item.value for item in AuditAction}
    assert domain_actions == {
        item.value
        for item in AuditAction
        if item.value.startswith(("purchase_intent.", "offer.", "transaction."))
    }
