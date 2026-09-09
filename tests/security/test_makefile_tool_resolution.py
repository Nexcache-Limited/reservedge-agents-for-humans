from __future__ import annotations

import ast
import os
import re
import subprocess
from pathlib import Path

import pytest

from itaa_validate_contracts.cli import main

REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
GENERATE_PY = (
    REPO_ROOT / "tools" / "validate-contracts" / "src" / "itaa_validate_contracts" / "generate.py"
)
FORBIDDEN_BINS = {"uv", "pnpm", "node", "npx", "corepack"}


def test_makefile_does_not_invoke_bare_uv_pnpm_or_node() -> None:
    for line in MAKEFILE.splitlines():
        if not line.startswith("\t"):
            continue
        body = line.lstrip("\t@").strip()
        if not body:
            continue
        command = body.split()[0]
        assert command not in FORBIDDEN_BINS, f"bare tool invocation: {line}"


def test_generate_py_does_not_invoke_bare_node_or_pnpm() -> None:
    tree = ast.parse(GENERATE_PY.read_text(encoding="utf-8"))
    forbidden = {"node", "pnpm", "npx", "corepack"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.List) or not node.elts:
            continue
        first = node.elts[0]
        if isinstance(first, ast.Constant) and first.value in forbidden:
            raise AssertionError(f"bare generator executable {first.value!r}")


def test_make_resolves_uv_without_local_bin_on_path() -> None:
    env = {
        "HOME": os.environ["HOME"],
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "USER": os.environ.get("USER", ""),
    }
    completed = subprocess.run(
        ["make", "-n", "format-check"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    assert re.search(r"/\S+/uv run ruff format --check", completed.stdout), completed.stdout


def test_make_passes_absolute_node_and_pnpm_into_contract_validation() -> None:
    env = {
        "HOME": os.environ["HOME"],
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "USER": os.environ.get("USER", ""),
    }
    completed = subprocess.run(
        ["make", "-n", "validate-contracts"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    assert re.search(r"--node-bin /\S+", completed.stdout), completed.stdout
    assert re.search(r"--pnpm-bin /\S+", completed.stdout), completed.stdout
    assert " --node-bin node" not in completed.stdout
    assert " --pnpm-bin pnpm" not in completed.stdout


def test_invalid_node_override_fails_without_traceback(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--skip-drift", "--node-bin", "/no/such/itaa-node"]) == 1
    err = capsys.readouterr().err
    assert "error: node was not found" in err
    assert "Traceback" not in err
    assert "FileNotFoundError" not in err


def test_invalid_pnpm_override_fails_without_traceback(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--skip-drift", "--pnpm-bin", "/no/such/itaa-pnpm"]) == 1
    err = capsys.readouterr().err
    assert "error: pnpm was not found" in err
    assert "Traceback" not in err
    assert "FileNotFoundError" not in err
