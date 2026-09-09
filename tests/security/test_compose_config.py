from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE = (REPO_ROOT / "compose.yaml").read_text(encoding="utf-8")


def test_compose_uses_postgres_only() -> None:
    assert "postgres:" in COMPOSE
    assert "image: postgres:" in COMPOSE
    assert "mysql" not in COMPOSE.lower()
    assert "mongo" not in COMPOSE.lower()
    assert "redis" not in COMPOSE.lower()


def test_compose_has_healthcheck_and_named_volume() -> None:
    assert "healthcheck:" in COMPOSE
    assert "pg_isready" in COMPOSE
    assert "itaa_pg_dev" in COMPOSE


def test_compose_has_no_product_schema() -> None:
    lowered = COMPOSE.lower()
    assert "create table" not in lowered
    assert "alembic" not in lowered
    assert "migration" not in lowered
