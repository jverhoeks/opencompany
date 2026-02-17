import asyncio
import logging
import os

from strands import Agent
from strands.models.litellm import LiteLLMModel

from opencompany.agents.prompts import build_system_prompt
from opencompany.models.db import Persona

logger = logging.getLogger(__name__)

# Tool registry -- maps tool names to actual tool functions
_TOOL_REGISTRY: dict = {}


def register_tool(name: str, func):
    _TOOL_REGISTRY[name] = func


def get_model(model_id: str | None = None) -> LiteLLMModel:
    return LiteLLMModel(
        client_args={
            "api_key": os.environ.get("OPENAI_API_KEY", ""),
            "api_base": os.environ.get("OPENAI_API_BASE", ""),
            "use_litellm_proxy": True,
        },
        model_id=model_id or os.environ.get("LITELLM_MODEL_ID", "azure/gpt-5"),
    )


def create_agent(
    persona: Persona,
    extra_tools: list | None = None,
    tools: dict | None = None,
) -> Agent:
    registry = tools if tools is not None else _TOOL_REGISTRY
    resolved_tools = []
    for tool_name in persona.tools:
        if tool_name in registry:
            resolved_tools.append(registry[tool_name])

    if extra_tools:
        resolved_tools.extend(extra_tools)

    logger.info("Created agent for persona %s with %d tools", persona.id, len(resolved_tools))
    return Agent(
        model=get_model(persona.model_id),
        system_prompt=build_system_prompt(persona),
        tools=resolved_tools,
        name=persona.name,
        description=f"{persona.role} ({persona.type})",
    )


async def run_persona(persona: Persona, task: str) -> str:
    logger.info("Running persona %s on task: %.80s", persona.id, task)
    agent = create_agent(persona)
    try:
        result = await asyncio.to_thread(agent, task)
        logger.info("Persona %s finished task", persona.id)
        return str(result)
    except Exception as e:
        logger.exception("Agent %s failed on task", persona.id)
        return f"Error: {e}"
