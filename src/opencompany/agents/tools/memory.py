"""Memory tools: allow personas to store and recall durable memories."""

from strands import tool


@tool
def remember(
    content: str,
    memory_type: str = "fact",
    related_to: str = "",
    persona_id: str = "",
) -> str:
    """Store a memory for future reference across runs.

    Use this to remember important facts, decisions, preferences, or interactions.

    Args:
        content: What to remember (be specific and concise)
        memory_type: Category — one of: fact, decision, interaction, preference
        related_to: Optional context — a ticket ID, persona ID, or topic
        persona_id: Your persona ID (the rememberer)
    """
    from opencompany.company.memory import store_memory
    from opencompany.utils import _run_async

    mem_id = _run_async(
        store_memory(
            persona_id=persona_id,
            type=memory_type,
            content=content,
            related_to=related_to or None,
        )
    )
    return f"Memory #{mem_id} stored ({memory_type}): {content[:80]}"


@tool
def recall(
    persona_id: str,
    memory_type: str = "",
    related_to: str = "",
    limit: int = 20,
) -> str:
    """Recall your stored memories from previous runs.

    Args:
        persona_id: Your persona ID
        memory_type: Filter by type (fact, decision, interaction, preference) — empty for all
        related_to: Filter by related context — empty for all
        limit: Maximum number of memories to return
    """
    from opencompany.company.memory import recall_memories
    from opencompany.utils import _run_async

    memories = _run_async(
        recall_memories(
            persona_id=persona_id,
            type=memory_type or None,
            related_to=related_to or None,
            limit=limit,
        )
    )
    if not memories:
        return "No memories found."

    lines = []
    for m in memories:
        prefix = f"[{m['type']}]"
        if m["related_to"]:
            prefix += f" (re: {m['related_to']})"
        lines.append(f"#{m['id']} {prefix} {m['content']}")
    return "\n".join(lines)
