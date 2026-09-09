"""Cloud-neutral ITAA observability package.

Audit vocabulary, redaction helpers, and an append-only sink port.
Standard library plus `itaa_domain` only. Hashing is applied by application
using the shared policy canonicalizer. An audit hash chain is tamper-evident
linkage, not signed non-repudiation or WORM storage.
"""

from __future__ import annotations

from itaa_domain import PACKAGE_NAME as DOMAIN_PACKAGE_NAME

PACKAGE_NAME = "itaa-observability"
PACKAGE_ROLE = "cloud-neutral-observability"
DOMAIN_DEPENDENCY = DOMAIN_PACKAGE_NAME

__all__ = ["DOMAIN_DEPENDENCY", "PACKAGE_NAME", "PACKAGE_ROLE"]
