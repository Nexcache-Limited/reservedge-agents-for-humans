"""Deterministic OpenAPI export and non-mutating drift check."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from itaa_api.app import create_app

EXPORT_PATH = Path(__file__).resolve().parents[2] / "openapi" / "itaa-v1.json"


def openapi_document() -> dict[str, Any]:
    return create_app().openapi()


def render_openapi() -> str:
    return json.dumps(openapi_document(), indent=2, sort_keys=True) + "\n"


def write_openapi(path: Path = EXPORT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_openapi(), encoding="utf-8")


def check_openapi(path: Path = EXPORT_PATH) -> int:
    expected = render_openapi()
    if not path.exists():
        sys.stderr.write("error: openapi export is missing\n")
        return 1
    actual = path.read_text(encoding="utf-8")
    if actual != expected:
        sys.stderr.write("error: openapi export drifted\n")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export or check ITAA local OpenAPI.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Non-mutating drift check against the committed export.",
    )
    args = parser.parse_args(argv)
    if args.check:
        return check_openapi()
    write_openapi()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
