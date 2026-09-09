"""Cloud-neutral ITAA policy package.

Deterministic disclosure, canonical hashing, approvals, supplier isolation, and
idempotency request binding. Standard library plus `itaa_domain` only.
"""

from __future__ import annotations

from itaa_domain import PACKAGE_NAME as DOMAIN_PACKAGE_NAME

PACKAGE_NAME = "itaa-policy"
PACKAGE_ROLE = "cloud-neutral-policy"
DOMAIN_DEPENDENCY = DOMAIN_PACKAGE_NAME

__all__ = ["DOMAIN_DEPENDENCY", "PACKAGE_NAME", "PACKAGE_ROLE"]
