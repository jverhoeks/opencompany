"""Durable persona memory: store, recall, and compact memories across runs."""

import logging

from sqlalchemy import delete, func, select

from opencompany.models.db import PersonaMemory
from opencompany.models.engine import async_session

logger = logging.getLogger(__name__)


async def store_memory(
    persona_id: str,
    type: str,
    content: str,
    related_to: str | None = None,
) -> int:
    """Save a memory entry to the database. Returns the memory ID."""
    async with async_session() as session:
        mem = PersonaMemory(
            persona_id=persona_id,
            type=type,
            content=content,
            related_to=related_to,
        )
        session.add(mem)
        await session.commit()
        await session.refresh(mem)
        logger.info("Stored memory #%d for %s (type=%s)", mem.id, persona_id, type)
        return mem.id


async def recall_memories(
    persona_id: str,
    type: str | None = None,
    related_to: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Retrieve memories for a persona, optionally filtered by type/related_to."""
    async with async_session() as session:
        q = select(PersonaMemory).where(PersonaMemory.persona_id == persona_id)
        if type:
            q = q.where(PersonaMemory.type == type)
        if related_to:
            q = q.where(PersonaMemory.related_to == related_to)
        q = q.order_by(PersonaMemory.created_at.desc()).limit(limit)
        result = await session.execute(q)
        return [
            {
                "id": m.id,
                "type": m.type,
                "content": m.content,
                "related_to": m.related_to,
                "created_at": m.created_at.isoformat(),
            }
            for m in result.scalars().all()
        ]


async def build_memory_context(persona_id: str, limit: int = 15) -> str:
    """Format recent memories as a text block for prompt injection."""
    memories = await recall_memories(persona_id, limit=limit)
    if not memories:
        return ""

    lines = ["[MEMORY — your retained knowledge from prior runs]"]
    for m in reversed(memories):  # oldest first
        prefix = f"[{m['type']}]"
        if m["related_to"]:
            prefix += f" (re: {m['related_to']})"
        lines.append(f"- {prefix} {m['content']}")
    lines.append("[END MEMORY]")
    return "\n".join(lines)


async def compact_memories(persona_id: str, threshold: int = 200, keep: int = 50) -> None:
    """When memory count exceeds threshold, summarize old entries into one and keep recent.

    Keeps the `keep` most recent memories and replaces the rest with a single
    summary entry.
    """
    async with async_session() as session:
        count = await session.scalar(
            select(func.count(PersonaMemory.id)).where(PersonaMemory.persona_id == persona_id)
        )
        if not count or count <= threshold:
            return

        # Get all memories ordered by created_at
        result = await session.execute(
            select(PersonaMemory)
            .where(PersonaMemory.persona_id == persona_id)
            .order_by(PersonaMemory.created_at.desc())
        )
        all_memories = result.scalars().all()

        # Split into keep (recent) and old
        recent_ids = {m.id for m in all_memories[:keep]}
        old_memories = [m for m in all_memories if m.id not in recent_ids]

        if not old_memories:
            return

        # Build summary from old memories
        summary_lines = []
        for m in reversed(old_memories):  # oldest first
            summary_lines.append(f"[{m.type}] {m.content}")

        summary_text = (
            f"Compacted {len(old_memories)} older memories:\n"
            + "\n".join(summary_lines[:50])  # cap summary size
        )
        if len(summary_lines) > 50:
            summary_text += f"\n... and {len(summary_lines) - 50} more entries"

        # Delete old memories
        old_ids = [m.id for m in old_memories]
        await session.execute(delete(PersonaMemory).where(PersonaMemory.id.in_(old_ids)))

        # Insert compacted summary
        session.add(
            PersonaMemory(
                persona_id=persona_id,
                type="compacted",
                content=summary_text,
            )
        )
        await session.commit()
        logger.info(
            "Compacted %d memories for %s (kept %d recent)",
            len(old_memories),
            persona_id,
            len(recent_ids),
        )
