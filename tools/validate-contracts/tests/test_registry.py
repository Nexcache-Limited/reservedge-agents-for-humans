from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, cast

import pytest

from itaa_validate_contracts.paths import repo_root
from itaa_validate_contracts.schema import check_registry, validate_schema_documents


def _copy_contracts(tmp_path: Path) -> Path:
    dest = tmp_path / "packages" / "contracts"
    shutil.copytree(
        repo_root() / "packages" / "contracts",
        dest,
        ignore=shutil.ignore_patterns("generated", "__pycache__"),
    )
    return tmp_path


def _write_registry(root: Path, payload: dict[str, Any]) -> None:
    path = root / "packages" / "contracts" / "registry.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _load_registry(root: Path) -> dict[str, Any]:
    path = root / "packages" / "contracts" / "registry.json"
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def test_committed_registry_is_complete() -> None:
    assert check_registry() == []


def test_missing_registry_entry_is_rejected(tmp_path: Path) -> None:
    root = _copy_contracts(tmp_path)
    payload = _load_registry(root)
    payload["schemas"] = [
        item for item in payload["schemas"] if "offer.schema.json" not in str(item["path"])
    ]
    _write_registry(root, payload)
    messages = [item.message for item in check_registry(root)]
    assert any("missing schema entries" in message for message in messages)


def test_duplicate_registry_id_is_rejected(tmp_path: Path) -> None:
    root = _copy_contracts(tmp_path)
    payload = _load_registry(root)
    schemas = list(payload["schemas"])
    duplicate = dict(schemas[1])
    duplicate["path"] = "schemas/v1/duplicate.schema.json"
    schemas.append(duplicate)
    payload["schemas"] = schemas
    _write_registry(root, payload)
    messages = [item.message for item in check_registry(root)]
    assert any("duplicate schema ids" in message for message in messages)


def test_registry_path_outside_package_is_rejected(tmp_path: Path) -> None:
    root = _copy_contracts(tmp_path)
    payload = _load_registry(root)
    payload["schemas"][1]["path"] = "../../README.md"
    _write_registry(root, payload)
    messages = [item.message for item in check_registry(root)]
    assert any("outside packages/contracts" in message for message in messages)


def test_wrong_semantic_version_is_rejected(tmp_path: Path) -> None:
    root = _copy_contracts(tmp_path)
    payload = _load_registry(root)
    payload["schemas"][1]["semanticVersion"] = "2.0"
    _write_registry(root, payload)
    messages = [item.message for item in check_registry(root)]
    assert any("semanticVersion must be 1.0" in message for message in messages)


def test_meta_schema_validation_does_not_use_the_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("schema validation must not use the network")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    assert validate_schema_documents() == []
