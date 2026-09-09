from __future__ import annotations

from itaa_redact_check.cli import scan_text, scan_workspace


def test_allowlists_env_example_local_defaults() -> None:
    findings = scan_text(".env.example", "POSTGRES_PASSWORD=itaa_dev_only\n")
    assert findings == []


def test_detects_pem_private_key_in_arbitrary_text() -> None:
    text = "-----" + "BEGIN PRIVATE KEY" + "-----\nABCD\n"
    findings = scan_text("tmp/secret.pem", text)
    assert any(item.rule == "pem-private-key" for item in findings)


def test_detects_aws_access_key_pattern() -> None:
    text = "key=" + "AKIA" + "IOSFODNN7EXAMPLE" + "\n"
    findings = scan_text("tmp/aws.txt", text)
    assert any(item.rule == "aws-access-key" for item in findings)


def test_workspace_scan_is_clean() -> None:
    assert scan_workspace() == []
