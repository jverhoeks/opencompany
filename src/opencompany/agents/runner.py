import asyncio
import concurrent.futures
import logging
import os
import re

from strands import Agent
from strands.models.litellm import LiteLLMModel

from opencompany.agents.prompts import build_system_prompt
from opencompany.models.db import Persona

logger = logging.getLogger(__name__)

# Tool registry -- maps tool names to actual tool functions
_TOOL_REGISTRY: dict = {}

_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=int(os.environ.get("AGENT_MAX_WORKERS", "10"))
)


def register_tool(name: str, func):
    _TOOL_REGISTRY[name] = func


def get_model(model_id: str | None = None) -> LiteLLMModel:
    resolved = model_id
    if not resolved:
        try:
            from opencompany.company.config import load_company_config

            resolved = load_company_config().default_model or None
        except Exception:
            pass
    if not resolved:
        resolved = os.environ.get("LITELLM_MODEL_ID") or "azure/gpt-5"
    logger.debug("Model resolved: requested=%s → using=%s", model_id, resolved)
    return LiteLLMModel(
        client_args={
            "api_key": os.environ.get("OPENAI_API_KEY", ""),
            "api_base": os.environ.get("OPENAI_API_BASE", ""),
            "use_litellm_proxy": True,
        },
        model_id=resolved,
    )


def create_agent(
    persona: Persona,
    extra_tools: list | None = None,
    tools: dict | None = None,
) -> Agent:
    registry = tools if tools is not None else _TOOL_REGISTRY
    resolved_tools = []
    missing_tools = []
    for tool_name in persona.tools:
        if tool_name in registry:
            resolved_tools.append(registry[tool_name])
        else:
            missing_tools.append(tool_name)

    if extra_tools:
        resolved_tools.extend(extra_tools)

    if missing_tools:
        logger.debug("Persona %s: unresolved tools %s", persona.id, missing_tools)
    logger.info("Created agent for persona %s with %d tools", persona.id, len(resolved_tools))
    return Agent(
        model=get_model(persona.model_id),
        system_prompt=build_system_prompt(persona),
        tools=resolved_tools,
        name=persona.name,
        description=f"{persona.role} ({persona.type})",
    )


class AgentResult:
    """Agent run result with text and optional token metrics."""

    __slots__ = ("text", "input_tokens", "output_tokens", "total_time_ms")

    def __init__(
        self,
        text: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_time_ms: float = 0,
    ):
        self.text = text
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.total_time_ms = total_time_ms

    def __str__(self) -> str:
        return self.text


async def run_persona(persona: Persona, task: str) -> AgentResult:
    logger.info("Running persona %s on task: %.80s", persona.id, task)
    loop = asyncio.get_running_loop()
    agent = create_agent(persona)
    try:
        result = await loop.run_in_executor(_executor, agent, task)
        logger.info("Persona %s finished task", persona.id)
        text = str(result)
        # Strip LLM thinking tags from output
        text = re.sub(r"<thinking>[\s\S]*?</thinking>\s*", "", text).strip()

        # Extract token metrics if available
        input_tokens = 0
        output_tokens = 0
        total_time_ms = 0.0
        metrics = getattr(result, "metrics", None)
        if metrics:
            input_tokens = getattr(metrics, "input_tokens", 0) or 0
            output_tokens = getattr(metrics, "output_tokens", 0) or 0
            total_time_ms = getattr(metrics, "total_time", 0) or 0
            logger.info(
                "Persona %s tokens: in=%d out=%d time=%.0fms",
                persona.id,
                input_tokens,
                output_tokens,
                total_time_ms,
            )

        return AgentResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_time_ms=total_time_ms,
        )
    except Exception as e:
        logger.exception("Agent %s failed on task", persona.id)
        return AgentResult(text=f"Error: {e}")
