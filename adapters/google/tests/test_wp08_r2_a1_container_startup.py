"""Adversarial proof that production start uses the frozen venv, not uv."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
IMAGE = "itaa-wp08-google-smoke:local"
CONTAINER = "itaa-wp08-r2-a1-startup"


def _docker_available() -> str | None:
    docker = shutil.which("docker")
    if docker is None:
        return None
    probe = subprocess.run(
        [docker, "info"],
        check=False,
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        return None
    return docker


def _dockerfile() -> str:
    return (REPO / "infra" / "google" / "Dockerfile").read_text(encoding="utf-8")


def _command_lines(dockerfile: str) -> list[str]:
    return [line for line in dockerfile.splitlines() if line.startswith("CMD")]


def test_dockerfile_cmd_is_frozen_venv_uvicorn() -> None:
    dockerfile = _dockerfile()
    commands = _command_lines(dockerfile)
    assert len(commands) == 1
    command = commands[0]
    assert "uv run" not in command
    assert "uv sync" not in command
    assert "/app/.venv/bin/uvicorn" in command
    assert "USER nonroot" in dockerfile
    assert 'ENV PATH="/app/.venv/bin:${PATH}"' in dockerfile
    assert "ENV VIRTUAL_ENV=/app/.venv" in dockerfile
    run_lines = [line for line in dockerfile.splitlines() if line.startswith("RUN uv")]
    assert run_lines, dockerfile
    assert all("uv sync --frozen" in line for line in run_lines)


def test_production_startup_does_not_invoke_uv_or_mutate_venv(tmp_path: Path) -> None:
    docker = _docker_available()
    if docker is None:
        pytest.skip("docker unavailable: engine or CLI is not running")

    build_cmd = [
        docker,
        "build",
        "-f",
        "infra/google/Dockerfile",
        "-t",
        IMAGE,
        ".",
    ]
    if os.environ.get("ITAA_DOCKER_NO_CACHE") == "1":
        build_cmd.insert(2, "--no-cache")
    build = subprocess.run(
        build_cmd,
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
    )
    if build.returncode != 0:
        raise AssertionError(f"docker build failed: {build.stderr[-800:]}")

    inspect = subprocess.run(
        [docker, "image", "inspect", IMAGE, "--format", "{{json .Config}}"],
        check=True,
        capture_output=True,
        text=True,
    )
    config = json.loads(inspect.stdout)
    assert config["User"] in {"nonroot", "10001"}
    assert config["Cmd"] == [
        "sh",
        "-c",
        "exec /app/.venv/bin/uvicorn itaa_google_adapter.app:app --host 0.0.0.0 --port ${PORT}",
    ]
    path_env = next(item for item in config["Env"] if item.startswith("PATH="))
    assert path_env.split("=", 1)[1].startswith("/app/.venv/bin:")
    assert "VIRTUAL_ENV=/app/.venv" in config["Env"]

    before = subprocess.run(
        [
            docker,
            "run",
            "--rm",
            "--network=none",
            "--entrypoint",
            "/app/.venv/bin/python",
            IMAGE,
            "-c",
            (
                "import hashlib, pathlib;"
                "root=pathlib.Path('/app/.venv');"
                "assert not (root / 'bin' / 'uv').exists();"
                "digest=hashlib.sha256();"
                "paths=sorted(p for p in root.rglob('*') if p.is_file());"
                "[digest.update(bytes(p)+b'\\0'+p.read_bytes()) for p in paths];"
                "print(len(paths), digest.hexdigest(), flush=True)"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if before.returncode != 0:
        raise AssertionError(f"venv fingerprint failed: {before.stderr[-800:]}")
    venv_before = before.stdout.strip()

    trap = tmp_path / "uv"
    trap.write_text(
        "#!/bin/sh\n"
        "echo 'uv-trap: production startup must not invoke uv' >&2\n"
        'echo "$*" > /tmp/uv-invoked\n'
        "exit 99\n",
        encoding="utf-8",
    )
    trap.chmod(trap.stat().st_mode | stat.S_IEXEC)

    subprocess.run([docker, "rm", "-f", CONTAINER], check=False, capture_output=True)
    run = subprocess.run(
        [
            docker,
            "run",
            "-d",
            "--name",
            CONTAINER,
            "--network=none",
            "--read-only",
            "--tmpfs",
            "/tmp",
            "--tmpfs",
            "/home/nonroot",
            "--mount",
            f"type=bind,src={trap},dst=/usr/local/bin/uv,ro=true",
            "-e",
            "PORT=8080",
            "-e",
            "ITAA_GOOGLE_MODEL_MODE=fake",
            "-e",
            "PYTHONDONTWRITEBYTECODE=1",
            IMAGE,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    try:
        if run.returncode != 0:
            raise AssertionError(f"docker run failed: {run.stderr[-800:]}")
        deadline = time.time() + 30
        last_error = "no-response"
        probe = (
            "import urllib.error, urllib.request;"
            "live=urllib.request.urlopen('http://127.0.0.1:8080/healthz');"
            "ready=urllib.request.urlopen('http://127.0.0.1:8080/readyz');"
            "assert live.status==200 and ready.status==200;"
            "print('healthy', flush=True)"
        )
        while time.time() < deadline:
            inspect_running = subprocess.run(
                [docker, "inspect", "-f", "{{.State.Running}} {{.State.ExitCode}}", CONTAINER],
                check=False,
                capture_output=True,
                text=True,
            )
            state = inspect_running.stdout.strip()
            if state.startswith("false"):
                logs = subprocess.run(
                    [docker, "logs", CONTAINER],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                raise AssertionError(
                    "container exited during frozen-venv startup: "
                    f"{state} logs={logs.stdout[-400:]}{logs.stderr[-400:]}"
                )
            health = subprocess.run(
                [docker, "exec", CONTAINER, "/app/.venv/bin/python", "-c", probe],
                check=False,
                capture_output=True,
                text=True,
            )
            if health.returncode == 0 and "healthy" in health.stdout:
                break
            last_error = health.stderr.strip() or health.stdout.strip() or "not-ready"
            time.sleep(0.5)
        else:
            raise AssertionError(f"container did not become healthy: {last_error}")

        cmdline = subprocess.run(
            [
                docker,
                "exec",
                CONTAINER,
                "/app/.venv/bin/python",
                "-c",
                "print(open('/proc/1/cmdline','rb').read().replace(b'\\x00', b' ').decode())",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        assert "/app/.venv/bin/uvicorn" in cmdline
        assert "uv run" not in cmdline
        assert "uv sync" not in cmdline

        trap_probe = subprocess.run(
            [docker, "exec", CONTAINER, "sh", "-c", "test ! -e /tmp/uv-invoked"],
            check=False,
            capture_output=True,
            text=True,
        )
        assert trap_probe.returncode == 0, "startup invoked the uv trap"

        user = (
            subprocess.run(
                [docker, "exec", CONTAINER, "sh", "-c", "id -u && id -un"],
                check=True,
                capture_output=True,
                text=True,
            )
            .stdout.strip()
            .splitlines()
        )
        assert user[0] == "10001"
        assert user[1] == "nonroot"

        after = subprocess.run(
            [
                docker,
                "exec",
                CONTAINER,
                "/app/.venv/bin/python",
                "-c",
                (
                    "import hashlib, pathlib;"
                    "root=pathlib.Path('/app/.venv');"
                    "digest=hashlib.sha256();"
                    "paths=sorted(p for p in root.rglob('*') if p.is_file());"
                    "[digest.update(bytes(p)+b'\\0'+p.read_bytes()) for p in paths];"
                    "print(len(paths), digest.hexdigest(), flush=True)"
                ),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        assert after.stdout.strip() == venv_before
    finally:
        subprocess.run([docker, "rm", "-f", CONTAINER], check=False, capture_output=True, text=True)
