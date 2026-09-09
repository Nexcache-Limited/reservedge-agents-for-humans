"""Non-mutating generated-output drift detection."""

from __future__ import annotations

import filecmp
import tempfile
from pathlib import Path

from itaa_validate_contracts.errors import ContractViolation
from itaa_validate_contracts.generate import (
    committed_python_dir,
    committed_typescript_dir,
    generate_all,
)
from itaa_validate_contracts.paths import repo_root
from itaa_validate_contracts.tooling import ToolBins

_PACKAGING_METADATA = frozenset({"pyproject.toml"})


def _files(directory: Path) -> dict[str, Path]:
    if not directory.exists():
        return {}
    files: dict[str, Path] = {}
    for path in directory.rglob("*"):
        if not path.is_file() or path.name == ".DS_Store":
            continue
        if path.name in _PACKAGING_METADATA:
            continue
        if any(part == "__pycache__" or part.endswith(".pyc") for part in path.parts):
            continue
        files[path.relative_to(directory).as_posix()] = path
    return files


def _diff_trees(expected: Path, actual: Path, *, label: str) -> list[ContractViolation]:
    expected_files = _files(expected)
    actual_files = _files(actual)
    found: list[ContractViolation] = []
    missing = sorted(set(expected_files) - set(actual_files))
    extra = sorted(set(actual_files) - set(expected_files))
    if missing:
        found.append(
            ContractViolation(
                "generated",
                label,
                "/",
                "drift",
                f"committed files missing from regeneration: {missing}",
            )
        )
    if extra:
        found.append(
            ContractViolation(
                "generated",
                label,
                "/",
                "drift",
                f"regeneration produced uncommitted files: {extra}",
            )
        )
    for rel in sorted(set(expected_files) & set(actual_files)):
        if not filecmp.cmp(expected_files[rel], actual_files[rel], shallow=False):
            found.append(
                ContractViolation(
                    "generated",
                    label,
                    f"/{rel}",
                    "drift",
                    "generated output differs from committed representation",
                )
            )
    return found


def check_drift(
    root: Path | None = None, *, tools: ToolBins | None = None
) -> list[ContractViolation]:
    scratch = repo_root() / "tmp"
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="itaa-contracts-", dir=scratch) as tmp:
        tmp_path = Path(tmp)
        python_dest = tmp_path / "python"
        typescript_dest = tmp_path / "typescript"
        generate_all(python_dest, typescript_dest, root=root, tools=tools)
        return [
            *_diff_trees(committed_python_dir(root), python_dest, label="generated/python"),
            *_diff_trees(
                committed_typescript_dir(root), typescript_dest, label="generated/typescript"
            ),
        ]
