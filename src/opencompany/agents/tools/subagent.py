"""Sub-agent tool: spawn a short-lived agent for parallelisable sub-tasks."""

import asyncio
import logging

from strands import tool

logger = logging.getLogger(__name__)

# Concurrency limit per persona
_SUBAGENT_SEMAPHORES: dict[str, asyncio.Semaphore] = {}
_MAX_CONCURRENT_SUBAGENTS = 2


@tool
def spawn_subagent(
    task: str,
    role: str = "solver",
    budget_tokens: int = 2000,
    persona_id: str = "",
) -> str:
    """Spin up a short-lived sub-agent to handle a parallelisable sub-task.

    The sub-agent has limited tools (read_file, write_file, grep_code) and
    cannot hire, fire, create tickets, or contact the overseer.

    Use this for independent work like: writing CSS while you continue HTML,
    generating test data, or formatting documentation.

    Args:
        task: Clear description of what the sub-agent should do
        role: Role hint for the sub-agent (e.g. "solver", "writer")
        budget_tokens: Max output tokens for the sub-agent (default 2000)
        persona_id: Your persona ID (parent agent)
    """
    from opencompany.agents.runner import get_model
    from opencompany.utils import _run_async

    # Enforce concurrency limit
    if persona_id not in _SUBAGENT_SEMAPHORES:
        _SUBAGENT_SEMAPHORES[persona_id] = asyncio.Semaphore(_MAX_CONCURRENT_SUBAGENTS)
    sem = _SUBAGENT_SEMAPHORES[persona_id]

    if sem.locked():
        return (
            f"Cannot spawn sub-agent: already at max concurrent "
            f"sub-agents ({_MAX_CONCURRENT_SUBAGENTS}). "
            f"Wait for a running sub-agent to finish."
        )

    async def _run():
        from strands import Agent

        async with sem:
            model = get_model()
            sub = Agent(
                model=model,
                system_prompt=(
                    f"You are a specialist {role} sub-agent. "
                    f"Complete the task concisely within {budget_tokens} tokens. "
                    f"Return only your result. Do not create tickets or hire."
                ),
                tools=[],  # Sub-agents get no tools — pure reasoning
                name=f"subagent-{persona_id}",
                max_tokens=budget_tokens,
            )
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, sub, task)
            return str(result)

    try:
        result_text = _run_async(_run())
        logger.info(
            "Sub-agent for %s completed task: %.60s",
            persona_id,
            task,
        )
        return result_text
    except Exception as e:
        logger.exception("Sub-agent for %s failed", persona_id)
        return f"Sub-agent error: {e}"
