"""Company hooks: Strands lifecycle callbacks for budget tracking and observability.

Replaces the custom callback_handler with proper Strands hooks.
Provides AfterInvocation → budget consumption + persona.idle event,
and BeforeToolUse → WorkLog recording for the metrics panel.
"""

import logging

logger = logging.getLogger(__name__)


class CompanyHooks:
    """Hook provider for OpenCompany agent lifecycle events.

    Tracks token consumption per persona/ticket and publishes
    lifecycle events to the Redis bus.

    .. warning::

       ``on_invocation_complete`` consumes the same ``consume_tokens`` and
       ``_add_ticket_tokens`` helpers that ``engine._run_inner`` calls when
       an agent finishes. If you wire these hooks into the Strands ``Agent``,
       you MUST drop the token-consume block in ``_run_inner`` or set a
       sentinel on the ``AgentResult`` so one of the two paths short-circuits
       — otherwise every invocation double-charges the persona's daily budget
       and double-credits the ticket.
    """

    def __init__(self, persona_id: str, ticket_id: int | None = None):
        self.persona_id = persona_id
        self.ticket_id = ticket_id
        self.tool_calls: list[str] = []

    async def on_tool_use(self, tool_name: str) -> None:
        """Record every tool call for the metrics panel."""
        self.tool_calls.append(tool_name)
        logger.debug(
            "Hook: persona %s called tool %s (ticket=%s)",
            self.persona_id,
            tool_name,
            self.ticket_id,
        )

    async def on_invocation_complete(self, input_tokens: int, output_tokens: int) -> None:
        """After agent finishes: consume budget, record tokens, publish idle."""
        from opencompany.company.budget import consume_tokens

        total = input_tokens + output_tokens
        if total > 0:
            await consume_tokens(self.persona_id, input_tokens, output_tokens)

        if self.ticket_id and total > 0:
            from opencompany.company.engine import _add_ticket_tokens

            await _add_ticket_tokens(self.ticket_id, input_tokens, output_tokens)

        logger.info(
            "Hook: persona %s completed (in=%d, out=%d, tools=%d)",
            self.persona_id,
            input_tokens,
            output_tokens,
            len(self.tool_calls),
        )

    def summary(self) -> dict:
        """Return a summary of this hook session for logging."""
        return {
            "persona_id": self.persona_id,
            "ticket_id": self.ticket_id,
            "tool_calls": self.tool_calls,
            "tool_count": len(self.tool_calls),
        }


class HiringGuardrail:
    """Intercept hire_persona calls and steer the agent away when team has capacity.

    Instead of hard-blocking, injects corrective context so the agent
    can make a better decision (e.g. assign existing team members).
    """

    async def check_hire(self, tool_name: str, tool_args: dict) -> str | None:
        """Check if hiring should be allowed.

        Returns a steering message if hiring should be blocked, None if allowed.
        """
        if tool_name != "hire_persona":
            return None

        from opencompany.company.personas import capacity_ratio

        ratio = await capacity_ratio()
        if ratio < 1.5:
            msg = (
                f"SYSTEM GUARDRAIL: Current capacity ratio is {ratio:.1f}. "
                f"Team is sufficiently staffed. Do NOT hire. "
                f"Assign existing team members instead."
            )
            logger.warning("Hiring guardrail triggered: ratio=%.1f", ratio)
            return msg

        return None
