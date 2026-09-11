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


def test_detects_liteapi_key_pattern() -> None:
    prefix = "sand_"
    uuid = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    findings = scan_text("tmp/liteapi.env", f"ITAA_LITEAPI_API_KEY={prefix}{uuid}\n")
    assert any(item.rule == "liteapi-api-key" for item in findings)


def test_empty_liteapi_env_example_line_is_allowed() -> None:
    findings = scan_text(".env.example", "ITAA_LITEAPI_API_KEY=\n")
    assert findings == []


def test_empty_prioticket_env_example_line_is_allowed() -> None:
    line = "ITAA_PRIOTICKET_CLIENT_" + "SECRET="
    findings = scan_text(".env.example", line + "\n")
    assert findings == []


def test_detects_prioticket_secret_assignment() -> None:
    name = "ITAA_PRIOTICKET_CLIENT_" + "SECRET"
    findings = scan_text("tmp/prio.env", name + "=super-secret-value\n")
    assert any(item.rule == "prioticket-client-secret" for item in findings)


def test_workspace_scan_is_clean() -> None:
    assert scan_workspace() == []


def test_local_env_files_are_not_workspace_scanned() -> None:
    from itaa_redact_check.cli import _is_local_env_file

    assert _is_local_env_file(".env") is True
    assert _is_local_env_file(".env.local") is True
    assert _is_local_env_file(".env.example") is False
