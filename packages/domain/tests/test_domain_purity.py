from __future__ import annotations

import ast
from pathlib import Path

from boundaries import FORBIDDEN_DOMAIN_MODULES, scan_domain

DOMAIN_SRC = Path(__file__).resolve().parents[1] / "src" / "itaa_domain"
REPO_ROOT = Path(__file__).resolve().parents[3]

FORBIDDEN_CALLS = {
    ("datetime", "now"),
    ("datetime", "utcnow"),
    ("datetime", "today"),
    ("date", "today"),
    ("time", "time"),
    ("time", "sleep"),
    ("os", "getenv"),
    ("os", "environ"),
    ("random", "random"),
    ("random", "choice"),
    ("secrets", "token_hex"),
    ("uuid", "uuid4"),
    ("hashlib", "sha256"),
    ("hashlib", "new"),
}

FORBIDDEN_IMPORTS = FORBIDDEN_DOMAIN_MODULES | {
    "os",
    "sys",
    "pathlib",
    "random",
    "secrets",
    "socket",
    "ssl",
    "subprocess",
    "urllib",
    "http",
    "httpx",
    "requests",
    "hashlib",
    "uuid",
    "jsonschema",
    "pydantic",
    "fastapi",
    "sqlalchemy",
    "itaa_contracts_generated",
    "itaa_application",
}


def test_domain_pyproject_has_no_runtime_dependencies() -> None:
    text = (REPO_ROOT / "packages" / "domain" / "pyproject.toml").read_text(encoding="utf-8")
    start = text.index("dependencies = [")
    end = text.index("]", start)
    block = text[start:end]
    assert block.strip() == "dependencies = ["


def test_domain_tree_has_no_forbidden_imports() -> None:
    assert scan_domain(REPO_ROOT) == []
    violations: list[str] = []
    for path in DOMAIN_SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top in FORBIDDEN_IMPORTS:
                        violations.append(f"{path.name} imports {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                top = node.module.split(".")[0]
                if top in FORBIDDEN_IMPORTS:
                    violations.append(f"{path.name} imports {node.module}")
            elif isinstance(node, ast.Call):
                func = node.func
                if (
                    isinstance(func, ast.Attribute)
                    and isinstance(func.value, ast.Name)
                    and (func.value.id, func.attr) in FORBIDDEN_CALLS
                ):
                    violations.append(f"{path.name} calls {func.value.id}.{func.attr}")
                if isinstance(func, ast.Name) and func.id == "open":
                    violations.append(f"{path.name} calls open()")
    assert violations == []
