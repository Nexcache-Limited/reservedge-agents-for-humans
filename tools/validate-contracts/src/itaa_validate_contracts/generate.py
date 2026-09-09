"""Generate Python and TypeScript representations from canonical JSON Schema."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from itaa_validate_contracts.paths import contracts_root, repo_root
from itaa_validate_contracts.schema import load_registry
from itaa_validate_contracts.tooling import ToolBins, ToolResolutionError, resolve_tools

HEADER_PY = '''"""DO NOT EDIT.

Generated from packages/contracts/schemas. Regenerate with `make generate-contracts`.
"""
'''

HEADER_TS = """/* DO NOT EDIT.
 *
 * Generated from packages/contracts/schemas. Regenerate with `make generate-contracts`.
 */
"""

NAMESPACE = "https://contracts.itaa.invalid/v1/"


def _keep_timestamps_as_strings(source: str) -> str:
    """Keep UTC timestamps as strings so the canonical Z pattern remains enforceable.

    datamodel-code-generator maps JSON Schema format date-time to datetime, then
    still emits the Z pattern. Pydantic cannot apply a string pattern to datetime.
    JSON Schema remains the semantic source; this only preserves a usable Python shape.
    """
    without_import = source.replace("from datetime import datetime\n", "")
    unions = without_import.replace("        datetime,\n", "        str,\n")
    unions = unions.replace("RootModel[datetime]", "RootModel[str]")
    return unions.replace("datetime | None", "str | None")


def _run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
    except FileNotFoundError:
        raise ToolResolutionError(
            f"error: {command[0]} was not found.\n"
            "Install Node.js 22+ and pnpm 11.9.x, or pass --node-bin / --pnpm-bin."
        ) from None
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n"
            f"{completed.stdout}\n{completed.stderr}"
        )


def materialize_relative_schemas(dest: Path, *, root: Path | None = None) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for entry in load_registry(root):
        payload = json.loads(entry.abs_path.read_text(encoding="utf-8"))
        text = json.dumps(payload, indent=2)
        text = text.replace(NAMESPACE, "./")
        (dest / entry.abs_path.name).write_text(text + "\n", encoding="utf-8")


def generate_python(dest: Path, *, root: Path | None = None) -> None:
    repo = root or repo_root()
    staged = dest / "_schemas"
    preserved: dict[str, bytes] = {}
    if dest.exists():
        for name in ("pyproject.toml",):
            candidate = dest / name
            if candidate.is_file():
                preserved[name] = candidate.read_bytes()
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for name, content in preserved.items():
        (dest / name).write_bytes(content)
    materialize_relative_schemas(staged, root=root)
    output_pkg = dest / "itaa_contracts_generated"
    output_pkg.mkdir()
    document_entries = [entry for entry in load_registry(root) if entry.kind == "document"]
    for entry in document_entries:
        schema_file = staged / entry.abs_path.name
        module = entry.python_module.rsplit(".", 1)[-1]
        target = output_pkg / f"{module}.py"
        _run(
            [
                sys.executable,
                "-m",
                "datamodel_code_generator",
                "--input",
                str(schema_file),
                "--input-file-type",
                "jsonschema",
                "--output",
                str(target),
                "--output-model-type",
                "pydantic_v2.BaseModel",
                "--target-python-version",
                "3.12",
                "--use-standard-collections",
                "--use-union-operator",
                "--disable-timestamp",
                "--use-schema-description",
                "--strict-nullable",
                "--collapse-root-models",
                "--use-annotated",
            ],
            cwd=repo,
        )
        original = target.read_text(encoding="utf-8")
        target.write_text(HEADER_PY + _keep_timestamps_as_strings(original), encoding="utf-8")
    init_lines = [HEADER_PY, "from __future__ import annotations\n"]
    exports: list[str] = []
    for entry in document_entries:
        module = entry.python_module.rsplit(".", 1)[-1]
        class_name = entry.typescript_export
        init_lines.append(f"from itaa_contracts_generated.{module} import {class_name}\n")
        exports.append(class_name)
    init_lines.append(f"\n__all__ = {exports!r}\n")
    (output_pkg / "__init__.py").write_text("".join(init_lines), encoding="utf-8")
    (output_pkg / "py.typed").write_text("", encoding="utf-8")
    shutil.rmtree(staged)
    _run([sys.executable, "-m", "ruff", "format", str(output_pkg)], cwd=repo)


def generate_typescript(
    dest: Path, *, root: Path | None = None, tools: ToolBins | None = None
) -> None:
    repo = root or repo_root()
    bins = tools or resolve_tools()
    compiler = repo / "tools" / "validate-contracts" / "scripts" / "compile-ts-schema.mjs"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    staged = dest / "_schemas"
    materialize_relative_schemas(staged, root=root)
    parts = [HEADER_TS]
    env = bins.subprocess_env()
    for entry in load_registry(root):
        if entry.kind != "document":
            continue
        schema_file = staged / entry.abs_path.name
        out_file = dest / f"{entry.typescript_export}.generated.ts"
        _run(
            [
                str(bins.node),
                str(compiler),
                str(schema_file),
                entry.typescript_export,
                str(out_file),
            ],
            cwd=repo,
            env=env,
        )
        body = out_file.read_text(encoding="utf-8")
        parts.append(f"\n/* {entry.path} */\n")
        parts.append(body if body.endswith("\n") else body + "\n")
        out_file.unlink()
    (dest / "index.ts").write_text("".join(parts), encoding="utf-8")
    shutil.rmtree(staged)
    prettier_config = repo / ".prettierrc.json"
    prettier = repo / "node_modules" / "prettier" / "bin" / "prettier.cjs"
    if not prettier.is_file():
        raise ToolResolutionError(
            "error: workspace Prettier was not found.\n"
            "Run make setup so node_modules/prettier is installed."
        )
    _run(
        [
            str(bins.node),
            str(prettier),
            "--config",
            str(prettier_config),
            "--ignore-path",
            os.devnull,
            "--write",
            str(dest / "index.ts"),
        ],
        cwd=repo,
        env=env,
    )


def generate_all(
    python_dest: Path,
    typescript_dest: Path,
    *,
    root: Path | None = None,
    tools: ToolBins | None = None,
) -> None:
    generate_python(python_dest, root=root)
    generate_typescript(typescript_dest, root=root, tools=tools)


def committed_python_dir(root: Path | None = None) -> Path:
    return contracts_root(root) / "generated" / "python"


def committed_typescript_dir(root: Path | None = None) -> Path:
    return contracts_root(root) / "generated" / "typescript"
