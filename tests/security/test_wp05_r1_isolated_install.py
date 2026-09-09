from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from itaa_application.offer_boundary import accept_offer as _installed_probe_parent

REPO = Path(__file__).resolve().parents[2]
_ = _installed_probe_parent


@pytest.mark.security
def test_installed_application_imports_without_pytest_pythonpath(tmp_path: Path) -> None:
    wheels = tmp_path / "wheels"
    venv = tmp_path / "venv"
    wheels.mkdir()
    packages = [
        REPO / "packages" / "domain",
        REPO / "packages" / "ranking",
        REPO / "packages" / "policy",
        REPO / "packages" / "observability",
        REPO / "packages" / "contracts" / "generated" / "python",
        REPO / "packages" / "application",
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = ""
    env["PYTHONNOUSERSITE"] = "1"
    uv = shutil.which("uv") or env.get("UV", "uv")
    for package in packages:
        built = subprocess.run(
            [uv, "build", "--out-dir", str(wheels)],
            cwd=package,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if built.returncode != 0:
            raise AssertionError(built.stdout + built.stderr)
    subprocess.run([uv, "venv", str(venv)], check=True, cwd=tmp_path, env=env)
    python = venv / "bin" / "python"
    wheel_files = sorted(str(path) for path in wheels.glob("*.whl"))
    assert wheel_files
    installed = subprocess.run(
        [uv, "pip", "install", "--python", str(python), *wheel_files],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if installed.returncode != 0:
        raise AssertionError(installed.stdout + installed.stderr)
    probe = """
import sys
assert not any(part.endswith('generated/python') for part in sys.path)
from itaa_application.offer_boundary import accept_offer
from itaa_contracts_generated.offer import Offer
payload = {
  "schemaVersion": "1.0",
  "offerId": "of_01k2m3n4p5q6r7s8t9v0w1x2a1",
  "intentId": "pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
  "supplierToken": "sp_01k2m3n4p5q6r7s8t9v0w1x2b1",
  "version": 1,
  "status": "submitted",
  "price": {
    "subtotalMinor": 9800,
    "feesMinor": 1200,
    "taxMinor": 900,
    "totalMinor": 11900,
    "currency": "USD",
  },
  "service": {
    "lotType": "uncovered",
    "shuttleMinutes": 15,
    "distanceMeters": 2400,
    "availability": "confirmed_simulated",
    "addOns": [],
  },
  "terms": {"cancellation": "free_until_24h", "refund": "original_method"},
  "validFrom": "2026-08-20T16:00:00Z",
  "validUntil": "2026-08-21T16:00:00Z",
  "evidence": [{"type": "supplier_policy", "ref": "policy.parkdirect.v1"}],
  "simulation": True,
  "signature": "sg_01k2m3n4p5q6r7s8t9v0w1x2h1",
}
Offer.model_validate(payload)
assert callable(accept_offer)
"""
    completed = subprocess.run(
        [str(python), "-c", probe],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
