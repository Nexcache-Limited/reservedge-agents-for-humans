"""Non-credentialed checks against the installed google-adk 2.7.1 API shape."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ConfigDict

from itaa_google_adapter.live import ExplainOutput, ExtractOutput

_ADK_CONFIG_WARNING = "ignore:BaseAgentConfig is deprecated:DeprecationWarning"


@pytest.mark.filterwarnings(_ADK_CONFIG_WARNING)
def test_installed_adk_constructs_llm_agent_runner_and_session() -> None:
    from google.adk.agents import LlmAgent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService

    class Shape(BaseModel):
        model_config = ConfigDict(extra="forbid")
        explanation: str

    agent = LlmAgent(
        model="gemini-2.5-flash",
        name="itaa_r2_shape",
        instruction="Return structured output only. Do not use tools.",
        output_schema=Shape,
    )
    assert agent.output_schema is Shape
    tools = getattr(agent, "tools", None)
    assert not tools
    sessions = InMemorySessionService()
    runner = Runner(agent=agent, app_name="itaa-google-adapter", session_service=sessions)
    assert runner.agent is agent
    assert ExtractOutput is not ExplainOutput


def test_live_schemas_are_pydantic_models_for_output_schema() -> None:
    assert issubclass(ExtractOutput, BaseModel)
    assert issubclass(ExplainOutput, BaseModel)
    ExtractOutput.model_json_schema()
    ExplainOutput.model_json_schema()
