"""ITAA canonical contract validation and generation."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from itaa_validate_contracts.drift import check_drift
from itaa_validate_contracts.errors import ContractViolation
from itaa_validate_contracts.fixtures import validate_invalid_fixtures, validate_valid_fixtures
from itaa_validate_contracts.generate import (
    committed_python_dir,
    committed_typescript_dir,
    generate_all,
)
from itaa_validate_contracts.schema import check_registry, validate_schema_documents
from itaa_validate_contracts.tooling import ToolBins, ToolResolutionError, resolve_tools


def collect_violations(
    *, include_drift: bool = True, tools: ToolBins | None = None
) -> list[ContractViolation]:
    found: list[ContractViolation] = []
    found.extend(check_registry())
    if found:
        return found
    found.extend(validate_schema_documents())
    found.extend(validate_valid_fixtures())
    found.extend(validate_invalid_fixtures())
    if include_drift:
        found.extend(check_drift(tools=tools))
    return found


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ITAA canonical contract validation")
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Regenerate Python and TypeScript representations into the committed directories.",
    )
    parser.add_argument(
        "--skip-drift",
        action="store_true",
        help="Skip generated-output drift detection (used while regenerating).",
    )
    parser.add_argument(
        "--node-bin",
        default=None,
        help="Absolute Node executable. Defaults to ITAA_NODE_BIN, PATH, then fallbacks.",
    )
    parser.add_argument(
        "--pnpm-bin",
        default=None,
        help="Absolute pnpm executable. Defaults to ITAA_PNPM_BIN, PATH, then fallbacks.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        tools = resolve_tools(node_bin=args.node_bin, pnpm_bin=args.pnpm_bin)
        if args.generate:
            generate_all(committed_python_dir(), committed_typescript_dir(), tools=tools)
            print("PASS: generated Python and TypeScript representations from canonical schemas.")
            return 0
        violations = collect_violations(include_drift=not args.skip_drift, tools=tools)
    except ToolResolutionError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if violations:
        for item in violations:
            print(item.render(), file=sys.stderr)
        print(f"FAIL: {len(violations)} contract validation issue(s).", file=sys.stderr)
        return 1
    print(
        "PASS: JSON Schema 2020-12, registry, fixtures, invariants, and generated-output"
        " drift checks."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
