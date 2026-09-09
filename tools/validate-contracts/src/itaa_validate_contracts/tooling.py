"""Resolve Node and pnpm executables without depending on the caller PATH."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class ToolResolutionError(RuntimeError):
    """Raised when Node or pnpm cannot be resolved to a working executable."""


_FALLBACK_DIRS = (Path("/usr/local/bin"), Path("/opt/homebrew/bin"))
_ENV_KEYS = {"node": "ITAA_NODE_BIN", "pnpm": "ITAA_PNPM_BIN"}
_HINTS = {
    "node": (
        "Install Node.js 22+ so node --version succeeds, or pass --node-bin / set ITAA_NODE_BIN."
    ),
    "pnpm": (
        "Enable pnpm 11.9.x with: corepack enable && corepack prepare pnpm@11.9.0 --activate, "
        "or pass --pnpm-bin / set ITAA_PNPM_BIN."
    ),
}


@dataclass(frozen=True)
class ToolBins:
    node: Path
    pnpm: Path

    def subprocess_env(self) -> dict[str, str]:
        env = os.environ.copy()
        prefixes = [str(self.node.parent), str(self.pnpm.parent)]
        existing = env.get("PATH", "")
        parts = [*prefixes, existing] if existing else prefixes
        env["PATH"] = os.pathsep.join(parts)
        return env


def _unique(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    ordered: list[Path] = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(path)
    return ordered


def _candidates(name: str, override: str | None) -> list[Path]:
    if override:
        return [Path(override).expanduser()]
    env_value = os.environ.get(_ENV_KEYS[name])
    if env_value:
        return [Path(env_value).expanduser()]
    found: list[Path] = []
    which = shutil.which(name)
    if which:
        found.append(Path(which))
    found.extend(directory / name for directory in _FALLBACK_DIRS)
    found.append(Path.home() / ".local" / "bin" / name)
    return _unique(found)


def _working_executable(name: str, override: str | None, *, extra_path: str | None = None) -> Path:
    env = os.environ.copy()
    if extra_path:
        current = env.get("PATH", "")
        env["PATH"] = extra_path + os.pathsep + current if current else extra_path
    for candidate in _candidates(name, override):
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            continue
        try:
            completed = subprocess.run(
                [str(candidate), "--version"],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
        except OSError:
            continue
        if completed.returncode == 0:
            return candidate
    raise ToolResolutionError(f"error: {name} was not found.\n{_HINTS[name]}")


def resolve_tools(*, node_bin: str | None = None, pnpm_bin: str | None = None) -> ToolBins:
    node = _working_executable("node", node_bin)
    pnpm = _working_executable("pnpm", pnpm_bin, extra_path=str(node.parent))
    return ToolBins(node=node, pnpm=pnpm)
