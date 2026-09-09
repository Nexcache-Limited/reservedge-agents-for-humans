from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from itaa_google_adapter.app import create_google_app

REPO = Path(__file__).resolve().parents[3]


def test_dockerfile_installs_google_adapter_live_extra() -> None:
    dockerfile = (REPO / "infra" / "google" / "Dockerfile").read_text(encoding="utf-8")
    assert "uv sync --frozen --package itaa-google-adapter --extra live" in dockerfile
    assert "--package itaa-api" not in dockerfile or "itaa-google-adapter" in dockerfile
    command_lines = [line for line in dockerfile.splitlines() if line.startswith("CMD")]
    assert len(command_lines) == 1
    command = command_lines[0]
    assert "uv run" not in command
    assert "uv sync" not in command
    assert "/app/.venv/bin/uvicorn" in command
    assert "exec /app/.venv/bin/uvicorn" in command


def test_local_app_health_without_docker() -> None:
    client = TestClient(create_google_app())
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 200


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


def test_docker_build_and_healthz() -> None:
    docker = _docker_available()
    if docker is None:
        import pytest

        pytest.skip("docker unavailable: engine or CLI is not running")
    image = "itaa-wp08-google-smoke:local"
    name = "itaa-wp08-google-smoke"
    build = subprocess.run(
        [docker, "build", "-f", "infra/google/Dockerfile", "-t", image, "."],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
    )
    if build.returncode != 0:
        raise AssertionError(f"docker build failed: {build.stderr[-800:]}")
    subprocess.run([docker, "rm", "-f", name], check=False, capture_output=True, text=True)
    inspect = subprocess.run(
        [
            docker,
            "run",
            "--rm",
            "--network=none",
            "--entrypoint",
            "/app/.venv/bin/python",
            image,
            "-c",
            "import google.adk; print(google.adk.__name__)",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if inspect.returncode != 0 or "google.adk" not in inspect.stdout:
        probe = subprocess.run(
            [
                docker,
                "run",
                "--rm",
                "--entrypoint",
                "python",
                image,
                "-c",
                (
                    "from google.adk.agents import LlmAgent;"
                    "from google.adk.runners import Runner;"
                    "from google.adk.sessions import InMemorySessionService;"
                    "from pydantic import BaseModel;"
                    "class Out(BaseModel):\n    explanation: str\n"
                    "agent=LlmAgent(model='gemini-2.5-flash',name='itaa_r2',"
                    "instruction='x',output_schema=Out);"
                    "Runner(agent=agent,app_name='itaa',session_service=InMemorySessionService());"
                    "print('constructed')"
                ),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if probe.returncode != 0:
            raise AssertionError("production image must contain google.adk")
    run = subprocess.run(
        [
            docker,
            "run",
            "-d",
            "--name",
            name,
            "-e",
            "PORT=8080",
            "-e",
            "ITAA_GOOGLE_MODEL_MODE=fake",
            "-p",
            "18080:8080",
            image,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    live_name = f"{name}-live"
    try:
        if run.returncode != 0:
            raise AssertionError(f"docker run failed: {run.stderr[-800:]}")
        deadline = time.time() + 30
        last_error = "no-response"
        while time.time() < deadline:
            try:
                live = httpx.get("http://127.0.0.1:18080/healthz", timeout=1.0)
                ready = httpx.get("http://127.0.0.1:18080/readyz", timeout=1.0)
                assert live.status_code == 200
                assert ready.status_code == 200
                break
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                time.sleep(0.5)
        else:
            raise AssertionError(f"container did not become healthy: {last_error}")
        subprocess.run([docker, "rm", "-f", live_name], check=False, capture_output=True, text=True)
        live_run = subprocess.run(
            [
                docker,
                "run",
                "-d",
                "--name",
                live_name,
                "-e",
                "PORT=8080",
                "-e",
                "ITAA_GOOGLE_MODEL_MODE=live",
                "-p",
                "18081:8080",
                image,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if live_run.returncode != 0:
            raise AssertionError(f"live container run failed: {live_run.stderr[-800:]}")
        deadline = time.time() + 30
        last_error = "no-response"
        while time.time() < deadline:
            try:
                ready = httpx.get("http://127.0.0.1:18081/readyz", timeout=1.0)
                assert ready.status_code == 503
                body = ready.json()
                assert body["status"] == "unavailable"
                assert body["adapter"] == "live"
                return
            except AssertionError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                time.sleep(0.5)
        raise AssertionError(f"live container did not refuse readiness: {last_error}")
    finally:
        subprocess.run([docker, "rm", "-f", name], check=False, capture_output=True, text=True)
        subprocess.run([docker, "rm", "-f", live_name], check=False, capture_output=True, text=True)
