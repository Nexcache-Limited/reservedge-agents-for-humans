"""Cloud-neutral ITAA application ports and governance services.

This package may depend on `itaa_domain`, `itaa_policy`, `itaa_observability`,
`itaa_ranking`, and the installable generated WP-02 package
`itaa-contracts-generated` at the Offer boundary.
It must not import adapters, FastAPI, ORM/database clients, cloud SDKs, RevenueCat,
the supplier-simulator app, or UI packages. In-memory repositories used by tests
are not production adapters.
"""

from __future__ import annotations

from itaa_application.approval_service import ApprovalService
from itaa_application.audit_service import AuditService
from itaa_application.dispatch_service import DispatchService
from itaa_application.idempotency_service import IdempotencyService
from itaa_application.offer_boundary import accept_offer
from itaa_application.ranking_decision import decide
from itaa_application.solicitation_service import SolicitationCollector
from itaa_domain import PACKAGE_NAME as DOMAIN_PACKAGE_NAME
from itaa_observability import PACKAGE_NAME as OBSERVABILITY_PACKAGE_NAME
from itaa_policy import PACKAGE_NAME as POLICY_PACKAGE_NAME
from itaa_ranking import PACKAGE_NAME as RANKING_PACKAGE_NAME

PACKAGE_NAME = "itaa-application"
PACKAGE_ROLE = "cloud-neutral-application"
DOMAIN_DEPENDENCY = DOMAIN_PACKAGE_NAME
POLICY_DEPENDENCY = POLICY_PACKAGE_NAME
OBSERVABILITY_DEPENDENCY = OBSERVABILITY_PACKAGE_NAME
RANKING_DEPENDENCY = RANKING_PACKAGE_NAME
CONTRACTS_DEPENDENCY = "itaa-contracts-generated"

__all__ = [
    "ApprovalService",
    "AuditService",
    "DispatchService",
    "DOMAIN_DEPENDENCY",
    "IdempotencyService",
    "OBSERVABILITY_DEPENDENCY",
    "PACKAGE_NAME",
    "PACKAGE_ROLE",
    "POLICY_DEPENDENCY",
    "RANKING_DEPENDENCY",
    "CONTRACTS_DEPENDENCY",
    "SolicitationCollector",
    "accept_offer",
    "decide",
]
