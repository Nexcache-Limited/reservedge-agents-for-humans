from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEST = REPO / "artifacts" / "comp-aws-06-sandbox"
APACHE = REPO / "docs/submissions-aws/public-export/LICENSE.Apache-2.0"
NOTICE = REPO / "NOTICE"

EXCLUDE_DIR_NAMES = {
    ".git",
    ".venv",
    "node_modules",
    ".pnpm-store",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".coverage",
    "htmlcov",
    "dist",
    "build",
    "docker-data",
    "artifacts",
    ".claude",
    "agent-transcripts",
}

EXCLUDE_FILE_NAMES = {
    ".env",
    "uv.lock.bin",
}

EXCLUDE_SUFFIXES = {".pem", ".p12", ".key", ".log"}

OPERATOR_DOCS = {
    "docs/submissions-aws/LIVE_BEDROCK_PRECHECK.md",
    "docs/submissions-aws/LIVE_BEDROCK_IAM_DESIGN.md",
    "docs/submissions-aws/LIVE_BEDROCK_AGREEMENT_STATUS.md",
    "docs/submissions-aws/BUILDER_ID.md",
    "docs/demo-aws/LIVE_RECORDING.md",
}


def _ignored(path: Path) -> bool:
    rel = path.relative_to(REPO).as_posix()
    if rel in OPERATOR_DOCS:
        return True
    if path.name in EXCLUDE_FILE_NAMES:
        return True
    if path.suffix in EXCLUDE_SUFFIXES:
        return True
    if path.name.startswith(".env.") and path.name != ".env.example":
        return True
    if "/iam/" in f"/{rel}/" and rel.startswith("docs/submissions-aws/iam/"):
        return True
    if rel.startswith("docs/submissions-aws/public-export/"):
        return True
    if rel.startswith("docs/work-orders/"):
        return True
    if rel.startswith("docs/deployment-evidence/"):
        return True
    if rel.startswith("docs/design/proposals/"):
        return True
    if rel.startswith("docs/submissions/") and not rel.startswith("docs/submissions-aws/"):
        return True
    parts = set(path.relative_to(REPO).parts)
    return bool(parts & EXCLUDE_DIR_NAMES)


def prepare(destination: Path = DEST) -> Path:
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    for src in REPO.rglob("*"):
        if _ignored(src) or not src.is_file():
            continue
        rel = src.relative_to(REPO)
        if any(part in EXCLUDE_DIR_NAMES for part in rel.parts):
            continue
        target = destination / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
    if not APACHE.is_file() or not NOTICE.is_file():
        raise FileNotFoundError("Apache-2.0 LICENSE template and NOTICE are required")
    shutil.copy2(APACHE, destination / "LICENSE")
    shutil.copy2(NOTICE, destination / "NOTICE")
    note = destination / "COMP-AWS-06-EXPORT-README.md"
    note.write_text(
        "\n".join(
            [
                "# COMP-AWS-06 local sandbox (not published)",
                "",
                "This copy was prepared locally. It is not a public repository.",
                "LICENSE is Apache-2.0. NOTICE is included.",
                "Operator IAM/Bedrock files, Builder ID, and LIVE_RECORDING.md were omitted.",
                "Hosted staging is process-local. AgentCore is not deployed.",
                "Do not publish this tree until Product Owner authorizes the public push.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return destination


def main() -> int:
    dest = prepare()
    print(f"prepared {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
