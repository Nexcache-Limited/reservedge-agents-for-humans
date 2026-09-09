"""Load registry.json and canonical schemas with local $id resolution."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import FormatChecker
from jsonschema.validators import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from itaa_validate_contracts.errors import ContractViolation
from itaa_validate_contracts.paths import contracts_root

DOCUMENT_KEYS = (
    "purchase-intent",
    "offer",
    "counter-offer",
    "acceptance",
    "transaction-authorization",
)

PHASE1_DOCUMENT_KEYS = (
    "orchestration-intent",
    "conversation",
    "intent-plan",
    "booking-task",
    "cost-ledger",
    "buyer-offer",
)

REQUIRED_SCHEMA_REL = {
    "schemas/v1/common.schema.json",
    "schemas/v1/purchase-intent.schema.json",
    "schemas/v1/offer.schema.json",
    "schemas/v1/counter-offer.schema.json",
    "schemas/v1/acceptance.schema.json",
    "schemas/v1/transaction-authorization.schema.json",
}

PHASE1_SCHEMA_REL = {
    "schemas/v1/orchestration-intent.schema.json",
    "schemas/v1/conversation.schema.json",
    "schemas/v1/intent-plan.schema.json",
    "schemas/v1/booking-task.schema.json",
    "schemas/v1/cost-ledger.schema.json",
    "schemas/v1/buyer-offer.schema.json",
}

ALLOWED_SCHEMA_REL = REQUIRED_SCHEMA_REL | PHASE1_SCHEMA_REL

FORMAT_CHECKER = FormatChecker()


@FORMAT_CHECKER.checks("date-time", raises=ValueError)
def is_rfc3339_date_time(instance: object) -> bool:
    """Validate calendar/clock values. The schema pattern still requires canonical Z form."""
    if not isinstance(instance, str):
        return True
    normalized = instance[:-1] + "+00:00" if instance.endswith("Z") else instance
    datetime.fromisoformat(normalized)
    return True


@dataclass(frozen=True)
class RegistryEntry:
    schema_id: str
    semantic_version: str
    path: str
    kind: str
    python_module: str
    typescript_export: str
    abs_path: Path


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_registry(root: Path | None = None) -> list[RegistryEntry]:
    contracts = contracts_root(root)
    payload = load_json(contracts / "registry.json")
    entries: list[RegistryEntry] = []
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for raw in payload["schemas"]:
        rel = str(raw["path"])
        schema_id = str(raw["id"])
        abs_path = (contracts / rel).resolve()
        entries.append(
            RegistryEntry(
                schema_id=schema_id,
                semantic_version=str(raw["semanticVersion"]),
                path=rel,
                kind=str(raw["kind"]),
                python_module=str(raw["pythonModule"]),
                typescript_export=str(raw["typescriptExport"]),
                abs_path=abs_path,
            )
        )
        seen_ids.add(schema_id)
        seen_paths.add(rel)
    if len(seen_ids) != len(entries):
        raise ValueError("registry contains duplicate schema ids")
    if len(seen_paths) != len(entries):
        raise ValueError("registry contains duplicate schema paths")
    return entries


def check_registry(root: Path | None = None) -> list[ContractViolation]:
    contracts = contracts_root(root)
    violations: list[ContractViolation] = []
    try:
        entries = load_registry(root)
    except Exception as exc:  # noqa: BLE001 - registry errors are reported as violations
        return [
            ContractViolation(
                schema_key="registry",
                source="registry.json",
                path="/",
                keyword="registry",
                message=str(exc),
            )
        ]
    found_rel = {entry.path for entry in entries}
    missing = REQUIRED_SCHEMA_REL - found_rel
    extra = found_rel - ALLOWED_SCHEMA_REL
    if missing:
        violations.append(
            ContractViolation(
                "registry",
                "registry.json",
                "/",
                "registry",
                f"missing schema entries: {sorted(missing)}",
            )
        )
    if extra:
        violations.append(
            ContractViolation(
                "registry",
                "registry.json",
                "/",
                "registry",
                f"unexpected schema entries: {sorted(extra)}",
            )
        )
    for entry in entries:
        if entry.semantic_version != "1.0":
            violations.append(
                ContractViolation(
                    "registry",
                    "registry.json",
                    f"/{entry.path}",
                    "registry",
                    f"semanticVersion must be 1.0, got {entry.semantic_version}",
                )
            )
        try:
            entry.abs_path.relative_to(contracts.resolve())
        except ValueError:
            violations.append(
                ContractViolation(
                    "registry",
                    "registry.json",
                    f"/{entry.path}",
                    "registry",
                    "schema path points outside packages/contracts",
                )
            )
            continue
        if not entry.abs_path.is_file():
            violations.append(
                ContractViolation(
                    "registry",
                    "registry.json",
                    f"/{entry.path}",
                    "registry",
                    "schema file does not exist",
                )
            )
            continue
        schema = load_json(entry.abs_path)
        if schema.get("$id") != entry.schema_id:
            violations.append(
                ContractViolation(
                    "registry",
                    entry.path,
                    "/$id",
                    "registry",
                    "schema $id does not match registry id",
                )
            )
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            violations.append(
                ContractViolation(
                    "registry",
                    entry.path,
                    "/$schema",
                    "registry",
                    "schema must declare JSON Schema 2020-12",
                )
            )
    return violations


def referencing_registry(root: Path | None = None) -> Registry:
    resources: list[tuple[str, Resource[Any]]] = []
    for entry in load_registry(root):
        contents = load_json(entry.abs_path)
        resources.append(
            (entry.schema_id, Resource.from_contents(contents, default_specification=DRAFT202012))
        )
    return Registry().with_resources(resources)


def schema_key_for_entry(entry: RegistryEntry) -> str:
    name = Path(entry.path).name.removesuffix(".schema.json")
    return name


def pointer_from_error(error: Any) -> str:
    parts = [str(item) for item in error.absolute_path]
    pointer = "/" + "/".join(parts) if parts else "/"
    validator = str(error.validator)
    message = str(error.message)
    if validator in {"additionalProperties", "required"} and "'" in message:
        name = message.split("'")[1]
        if pointer == "/":
            return f"/{name}"
        return f"{pointer}/{name}"
    return pointer


def _iter_errors(error: Any) -> list[Any]:
    found = [error]
    for child in error.context or []:
        found.extend(_iter_errors(child))
    return found


def validate_instance(
    document: Any,
    *,
    schema_key: str,
    source: str,
    root: Path | None = None,
) -> list[ContractViolation]:
    entries = {schema_key_for_entry(entry): entry for entry in load_registry(root)}
    entry = entries[schema_key]
    schema = load_json(entry.abs_path)
    validator = Draft202012Validator(
        schema,
        registry=referencing_registry(root),
        format_checker=FORMAT_CHECKER,
    )
    found: list[ContractViolation] = []
    for error in validator.iter_errors(document):
        for item in _iter_errors(error):
            found.append(
                ContractViolation(
                    schema_key=schema_key,
                    source=source,
                    path=pointer_from_error(item),
                    keyword=str(item.validator),
                    message=item.message,
                )
            )
    return found


def validate_schema_documents(root: Path | None = None) -> list[ContractViolation]:
    found: list[ContractViolation] = []
    for entry in load_registry(root):
        schema = load_json(entry.abs_path)
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as exc:  # noqa: BLE001
            found.append(
                ContractViolation(
                    schema_key=schema_key_for_entry(entry),
                    source=entry.path,
                    path="/",
                    keyword="meta-schema",
                    message=str(exc),
                )
            )
    return found
