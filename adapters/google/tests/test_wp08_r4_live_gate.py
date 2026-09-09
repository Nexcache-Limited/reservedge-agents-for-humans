"""Always-on live-gate source checks. The credentialed module stays skip-gated."""

from __future__ import annotations

from pathlib import Path

from itaa_google_adapter.resilience import FAKE_TIMEOUT_MS, ResiliencePolicy

LIVE_TEST = Path(__file__).with_name("test_wp08_live_gemini.py")


def test_fake_resilience_timeout_stays_fast() -> None:
    policy = ResiliencePolicy()
    assert policy.timeout_ms == FAKE_TIMEOUT_MS
    assert policy.timeout_ms == 2_000
    assert policy.max_attempts == 2


def test_credentialed_live_module_is_opt_in_and_strict() -> None:
    source = LIVE_TEST.read_text(encoding="utf-8")
    assert "pytest.mark.skipif" in source
    assert 'os.environ.get("ITAA_GOOGLE_LIVE_TEST") != "1"' in source
    assert "ITAA_GOOGLE_TIMEOUT_MS" in source
    assert "LIVE_RUNS = 3" in source
    assert "except ApplicationError" not in source
    assert 'assert exc.field == "model"' not in source
    assert "FakeModel" in source
    assert "LIVE_VERTEX_OK" in source
    assert "JFK_TEXT" in source
    assert "example-gcp-project" not in source
    assert "timeout_ms=LIVE_TEST_DEADLINE_MS" not in source
    assert "ResiliencePolicy(timeout_ms=" not in source


def test_live_llm_agent_is_constructed_without_tools() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "src" / "itaa_google_adapter" / "live.py"
    ).read_text(encoding="utf-8")
    start = source.index("agent = llm_agent_cls(")
    end = source.index("session_service = session_cls()")
    block = source[start:end]
    assert "output_schema=schema" in block
    assert "generate_content_config=" in block
    assert "tools=" not in block
    assert "timeout=" not in block
