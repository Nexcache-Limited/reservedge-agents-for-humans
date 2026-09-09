"""Dependency-direction checker for ITAA core packages."""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

FORBIDDEN_CORE_MODULES: Final[frozenset[str]] = frozenset(
    {
        "fastapi",
        "starlette",
        "uvicorn",
        "sqlalchemy",
        "alembic",
        "psycopg",
        "psycopg2",
        "asyncpg",
        "boto3",
        "botocore",
        "google",
        "strands",
        "bedrock",
        "anthropic",
        "openai",
        "revenuecat",
        "purchases",
        "react",
        "expo",
        "cloudflare",
        "vercel",
    }
)

FORBIDDEN_DOMAIN_MODULES: Final[frozenset[str]] = FORBIDDEN_CORE_MODULES | {
    "itaa_application",
    "itaa_ranking",
    "itaa_supplier_simulator",
    "itaa_validate_contracts",
    "itaa_redact_check",
    "itaa_contracts_generated",
    "pydantic",
    "jsonschema",
}

FORBIDDEN_APPLICATION_MODULES: Final[frozenset[str]] = FORBIDDEN_CORE_MODULES | {
    "itaa_supplier_simulator",
}

FORBIDDEN_RANKING_MODULES: Final[frozenset[str]] = FORBIDDEN_CORE_MODULES | {
    "itaa_application",
    "itaa_policy",
    "itaa_observability",
    "itaa_validate_contracts",
    "itaa_redact_check",
    "itaa_contracts_generated",
    "itaa_supplier_simulator",
    "pydantic",
    "jsonschema",
}

FORBIDDEN_POLICY_MODULES: Final[frozenset[str]] = FORBIDDEN_CORE_MODULES | {
    "itaa_application",
    "itaa_observability",
    "itaa_ranking",
    "itaa_supplier_simulator",
    "itaa_validate_contracts",
    "itaa_redact_check",
    "itaa_contracts_generated",
    "pydantic",
    "jsonschema",
}

FORBIDDEN_OBSERVABILITY_MODULES: Final[frozenset[str]] = FORBIDDEN_CORE_MODULES | {
    "itaa_application",
    "itaa_policy",
    "itaa_ranking",
    "itaa_supplier_simulator",
    "itaa_validate_contracts",
    "itaa_redact_check",
    "itaa_contracts_generated",
    "pydantic",
    "jsonschema",
}

FORBIDDEN_CONTRACTS_MODULES: Final[frozenset[str]] = FORBIDDEN_CORE_MODULES | {
    "itaa_domain",
    "itaa_application",
}

FORBIDDEN_DEPENDENCY_NAMES: Final[frozenset[str]] = frozenset(
    {
        "fastapi",
        "sqlalchemy",
        "psycopg",
        "psycopg2",
        "psycopg2-binary",
        "asyncpg",
        "boto3",
        "botocore",
        "google-cloud-aiplatform",
        "google-adk",
        "google-generativeai",
        "strands-agents",
        "amazon-bedrock",
        "revenuecat",
        "purchases",
        "expo",
        "react",
        "react-native",
        "react-dom",
        "@google-cloud/aiplatform",
        "@aws-sdk/client-bedrock-runtime",
    }
)


@dataclass(frozen=True)
class Violation:
    path: str
    message: str


def _top_level_module(name: str) -> str:
    return name.split(".")[0]


def imported_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(_top_level_module(alias.name))
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(_top_level_module(node.module))
    return names


def scan_python_file(path: Path, forbidden: frozenset[str]) -> list[Violation]:
    source = path.read_text(encoding="utf-8")
    found = imported_modules(source) & forbidden
    return [
        Violation(path=str(path), message=f"prohibited import '{name}'") for name in sorted(found)
    ]


def iter_python_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*.py"):
        if any(part in {".venv", "node_modules", "__pycache__"} for part in path.parts):
            continue
        yield path


def scan_tree(root: Path, forbidden: frozenset[str]) -> list[Violation]:
    violations: list[Violation] = []
    for path in iter_python_files(root):
        violations.extend(scan_python_file(path, forbidden))
    return violations


def _dependency_names_from_pyproject(text: str) -> set[str]:
    names: set[str] = set()
    in_dependencies = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line == "dependencies = [":
            in_dependencies = True
            continue
        if in_dependencies:
            if line.startswith("]"):
                in_dependencies = False
                continue
            match = re.search(r'"([A-Za-z0-9_.@/-]+)', line)
            if match:
                names.add(match.group(1).lower())
    return names


def scan_pyproject(path: Path) -> list[Violation]:
    if not path.exists():
        return []
    names = _dependency_names_from_pyproject(path.read_text(encoding="utf-8"))
    forbidden = names & {item.lower() for item in FORBIDDEN_DEPENDENCY_NAMES}
    return [
        Violation(path=str(path), message=f"prohibited dependency '{name}'")
        for name in sorted(forbidden)
    ]


def scan_package_json(path: Path) -> list[Violation]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    combined = {
        **payload.get("dependencies", {}),
        **payload.get("devDependencies", {}),
        **payload.get("peerDependencies", {}),
    }
    violations: list[Violation] = []
    for name in combined:
        if name.lower() in {item.lower() for item in FORBIDDEN_DEPENDENCY_NAMES}:
            violations.append(Violation(path=str(path), message=f"prohibited dependency '{name}'"))
    return violations


def scan_domain(root: Path) -> list[Violation]:
    domain = root / "packages" / "domain"
    return [
        *scan_tree(domain, FORBIDDEN_DOMAIN_MODULES),
        *scan_pyproject(domain / "pyproject.toml"),
    ]


def scan_policy(root: Path) -> list[Violation]:
    policy = root / "packages" / "policy"
    return [
        *scan_tree(policy / "src", FORBIDDEN_POLICY_MODULES),
        *scan_pyproject(policy / "pyproject.toml"),
    ]


def scan_observability(root: Path) -> list[Violation]:
    observability = root / "packages" / "observability"
    return [
        *scan_tree(observability / "src", FORBIDDEN_OBSERVABILITY_MODULES),
        *scan_pyproject(observability / "pyproject.toml"),
    ]


def scan_application(root: Path) -> list[Violation]:
    application = root / "packages" / "application"
    return [
        *scan_tree(application, FORBIDDEN_APPLICATION_MODULES),
        *scan_pyproject(application / "pyproject.toml"),
    ]


def scan_ranking(root: Path) -> list[Violation]:
    ranking = root / "packages" / "ranking"
    return [
        *scan_tree(ranking / "src", FORBIDDEN_RANKING_MODULES),
        *scan_pyproject(ranking / "pyproject.toml"),
    ]


def scan_contracts(root: Path) -> list[Violation]:
    contracts = root / "packages" / "contracts"
    return [
        *scan_tree(contracts, FORBIDDEN_CONTRACTS_MODULES),
        *scan_package_json(contracts / "package.json"),
    ]


def scan_ui_kit(root: Path) -> list[Violation]:
    return scan_package_json(root / "packages" / "ui-kit" / "package.json")
