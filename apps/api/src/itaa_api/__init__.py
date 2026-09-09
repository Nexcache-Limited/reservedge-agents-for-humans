"""Local simulation FastAPI composition. Not a production authorization surface."""

from __future__ import annotations

PACKAGE_NAME = "itaa-api"
PACKAGE_ROLE = "local-simulation-http"
ENVIRONMENT = "local_simulation"
DURABILITY = "unsupported"

__all__ = ["DURABILITY", "ENVIRONMENT", "PACKAGE_NAME", "PACKAGE_ROLE"]
