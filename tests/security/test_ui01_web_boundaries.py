from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "apps" / "web"


def test_ui01_web_forbids_vercel_google_aws_and_revenuecat() -> None:
    manifest = (WEB / "package.json").read_text(encoding="utf-8").lower()
    for needle in (
        "vercel",
        "@vercel",
        "google-adk",
        "google-generativeai",
        "boto3",
        "@aws-sdk",
        "revenuecat",
        "react-native",
        "expo",
    ):
        assert needle not in manifest


def test_ui01_web_uses_authorized_react_vite_stack() -> None:
    manifest = (WEB / "package.json").read_text(encoding="utf-8")
    assert '"react"' in manifest
    assert '"vite"' in manifest
    assert '"@itaa/ui-kit"' in manifest
