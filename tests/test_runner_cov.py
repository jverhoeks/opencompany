"""Extended coverage tests for agents/runner.py — create_agent, run_persona, AgentResult."""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from opencompany.agents.runner import (
    AgentResult,
    create_agent,
    register_tool,
    run_persona,
)
from opencompany.models.db import Persona


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_persona(**overrides) -> Persona:
    defaults = dict(
        id="dev-1",
        name="Jamie",
        role="Dev",
        type="solver",
        skills=["python"],
        backstory="Fast coder.",
        tools=["create_ticket", "read_file"],
    )
    defaults.update(overrides)
    return Persona(**defaults)


async def _fake_run_in_executor(executor, fn, *args):
    return fn(*args)


# ---------------------------------------------------------------------------
# register_tool
# ---------------------------------------------------------------------------
def test_register_tool():
    """register_tool adds a function to the global registry."""
    sentinel = lambda: None  # noqa: E731
    register_tool("_test_sentinel", sentinel)

    from opencompany.agents.runner import _TOOL_REGISTRY

    assert _TOOL_REGISTRY["_test_sentinel"] is sentinel
    # Cleanup
    _TOOL_REGISTRY.pop("_test_sentinel", None)


# ---------------------------------------------------------------------------
# get_model
# ---------------------------------------------------------------------------
def test_get_model_uses_env(monkeypatch):
    """get_model passes env vars and model_id to LiteLLMModel."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_BASE", "http://localhost:4000")
    monkeypatch.setenv("LITELLM_MODEL_ID", "gpt-test")

    with (
        patch("strands.models.litellm.LiteLLMModel") as MockModel,
        patch("opencompany.company.config.load_company_config", side_effect=FileNotFoundError),
    ):
        from opencompany.agents.runner import get_model

        get_model()
        MockModel.assert_called_once()
        call_kwargs = MockModel.call_args[1]
        assert call_kwargs["model_id"] == "gpt-test"
        assert call_kwargs["client_args"]["api_key"] == "test-key"


def test_get_model_explicit_model_id(monkeypatch):
    """get_model uses the explicit model_id over env var."""
    monkeypatch.setenv("LITELLM_MODEL_ID", "gpt-env")

    with patch("strands.models.litellm.LiteLLMModel") as MockModel:
        from opencompany.agents.runner import get_model

        get_model("gpt-explicit")
        call_kwargs = MockModel.call_args[1]
        assert call_kwargs["model_id"] == "gpt-explicit"


# ---------------------------------------------------------------------------
# create_agent — tool resolution
# ---------------------------------------------------------------------------
def test_create_agent_resolves_tools_from_registry():
    """create_agent picks tools from the registry matching persona.tools."""
    tool_a = MagicMock(name="tool_a")
    tool_b = MagicMock(name="tool_b")
    registry = {
        "create_ticket": tool_a,
        "read_file": tool_b,
        "other_tool": MagicMock(),
    }

    persona = _make_persona(tools=["create_ticket", "read_file"])

    with (
        patch("opencompany.agents.runner.get_model"),
        patch("strands.Agent") as MockAgent,
    ):
        create_agent(persona, tools=registry)
        call_kwargs = MockAgent.call_args[1]
        assert tool_a in call_kwargs["tools"]
        assert tool_b in call_kwargs["tools"]
        assert len(call_kwargs["tools"]) == 2


def test_create_agent_skips_missing_tools():
    """create_agent silently skips tool names not in the registry."""
    persona = _make_persona(tools=["nonexistent_tool"])
    registry = {"real_tool": MagicMock()}

    with (
        patch("opencompany.agents.runner.get_model"),
        patch("strands.Agent") as MockAgent,
    ):
        create_agent(persona, tools=registry)
        call_kwargs = MockAgent.call_args[1]
        assert len(call_kwargs["tools"]) == 0


def test_create_agent_extra_tools():
    """create_agent appends extra_tools to resolved tools."""
    extra = MagicMock(name="extra_tool")
    persona = _make_persona(tools=[])

    with (
        patch("opencompany.agents.runner.get_model"),
        patch("strands.Agent") as MockAgent,
    ):
        create_agent(persona, extra_tools=[extra], tools={})
        call_kwargs = MockAgent.call_args[1]
        assert extra in call_kwargs["tools"]


def test_create_agent_sets_name_and_description():
    """create_agent passes persona name and description to Agent."""
    persona = _make_persona(name="Dana Kim", role="Tech Lead", type="lead")

    with (
        patch("opencompany.agents.runner.get_model"),
        patch("strands.Agent") as MockAgent,
    ):
        create_agent(persona, tools={})
        call_kwargs = MockAgent.call_args[1]
        assert call_kwargs["name"] == "Dana Kim"
        assert "Tech Lead" in call_kwargs["description"]
        assert "lead" in call_kwargs["description"]


# ---------------------------------------------------------------------------
# AgentResult
# ---------------------------------------------------------------------------
def test_agent_result_defaults():
    """AgentResult stores text and defaults token metrics to zero."""
    r = AgentResult(text="hello")
    assert r.text == "hello"
    assert r.input_tokens == 0
    assert r.output_tokens == 0
    assert r.total_time_ms == 0
    assert str(r) == "hello"


def test_agent_result_with_metrics():
    """AgentResult stores token metrics when provided."""
    r = AgentResult(
        text="done",
        input_tokens=100,
        output_tokens=50,
        total_time_ms=1234.5,
    )
    assert r.input_tokens == 100
    assert r.output_tokens == 50
    assert r.total_time_ms == 1234.5
    assert str(r) == "done"


# ---------------------------------------------------------------------------
# run_persona — happy path
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_run_persona_happy_path():
    """run_persona returns AgentResult with text from agent call."""
    persona = _make_persona()

    fake_result = MagicMock()
    fake_result.__str__ = MagicMock(return_value="Task completed")
    fake_result.metrics = None

    fake_agent = MagicMock(side_effect=lambda task: fake_result)

    with patch(
        "opencompany.agents.runner.create_agent",
        return_value=fake_agent,
    ):
        loop = asyncio.get_running_loop()
        with patch.object(
            loop,
            "run_in_executor",
            side_effect=_fake_run_in_executor,
        ):
            result = await run_persona(persona, "Write some code")

    assert isinstance(result, AgentResult)
    assert result.text == "Task completed"


@pytest.mark.asyncio
async def test_run_persona_strips_thinking_tags():
    """run_persona strips <thinking> tags from agent output."""
    persona = _make_persona()

    fake_result = MagicMock()
    fake_result.__str__ = MagicMock(
        return_value=("<thinking>internal reasoning</thinking>\nFinal answer here")
    )
    fake_result.metrics = None

    fake_agent = MagicMock(side_effect=lambda t: fake_result)
    with patch(
        "opencompany.agents.runner.create_agent",
        return_value=fake_agent,
    ):
        loop = asyncio.get_running_loop()
        with patch.object(
            loop,
            "run_in_executor",
            side_effect=_fake_run_in_executor,
        ):
            result = await run_persona(persona, "Think and respond")

    assert "<thinking>" not in result.text
    assert "Final answer here" in result.text


@pytest.mark.asyncio
async def test_run_persona_extracts_token_metrics():
    """run_persona extracts token metrics from result.metrics."""
    persona = _make_persona()

    metrics = SimpleNamespace(input_tokens=200, output_tokens=80, total_time=500.0)
    fake_result = MagicMock()
    fake_result.__str__ = MagicMock(return_value="Done")
    fake_result.metrics = metrics

    fake_agent = MagicMock(side_effect=lambda t: fake_result)
    with patch(
        "opencompany.agents.runner.create_agent",
        return_value=fake_agent,
    ):
        loop = asyncio.get_running_loop()
        with patch.object(
            loop,
            "run_in_executor",
            side_effect=_fake_run_in_executor,
        ):
            result = await run_persona(persona, "Do work")

    assert result.input_tokens == 200
    assert result.output_tokens == 80
    assert result.total_time_ms == 500.0


@pytest.mark.asyncio
async def test_run_persona_error_handling():
    """run_persona catches exceptions and returns error AgentResult."""
    persona = _make_persona()

    def exploding_agent(task):
        raise RuntimeError("LLM exploded")

    fake_agent = MagicMock(side_effect=exploding_agent)
    with patch(
        "opencompany.agents.runner.create_agent",
        return_value=fake_agent,
    ):
        loop = asyncio.get_running_loop()
        with patch.object(
            loop,
            "run_in_executor",
            side_effect=_fake_run_in_executor,
        ):
            result = await run_persona(persona, "Fail task")

    assert isinstance(result, AgentResult)
    assert "Error" in result.text
    assert "LLM exploded" in result.text


@pytest.mark.asyncio
async def test_run_persona_metrics_with_none_values():
    """run_persona handles metrics with None values gracefully."""
    persona = _make_persona()

    metrics = SimpleNamespace(input_tokens=None, output_tokens=None, total_time=None)
    fake_result = MagicMock()
    fake_result.__str__ = MagicMock(return_value="Result")
    fake_result.metrics = metrics

    fake_agent = MagicMock(side_effect=lambda t: fake_result)
    with patch(
        "opencompany.agents.runner.create_agent",
        return_value=fake_agent,
    ):
        loop = asyncio.get_running_loop()
        with patch.object(
            loop,
            "run_in_executor",
            side_effect=_fake_run_in_executor,
        ):
            result = await run_persona(persona, "Work")

    assert result.input_tokens == 0
    assert result.output_tokens == 0
    assert result.total_time_ms == 0
