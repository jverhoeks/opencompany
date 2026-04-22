"""Tests for durable persona memory system."""

from unittest.mock import patch

from sqlalchemy.ext.asyncio import async_sessionmaker

from opencompany.models.db import Persona
from tests.conftest import mock_run_async


# ---------------------------------------------------------------------------
# Core memory functions
# ---------------------------------------------------------------------------
async def test_store_and_recall(db_engine):
    """Round-trip: store a memory and recall it."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="dev-mem",
                name="Dev",
                role="Dev",
                type="solver",
                backstory="A developer.",
            )
        )
        await session.commit()

    with patch("opencompany.company.memory.async_session", factory):
        from opencompany.company.memory import recall_memories, store_memory

        mem_id = await store_memory("dev-mem", "fact", "Python 3.14 is awesome")
        assert mem_id > 0

        memories = await recall_memories("dev-mem")
        assert len(memories) == 1
        assert memories[0]["content"] == "Python 3.14 is awesome"
        assert memories[0]["type"] == "fact"


async def test_recall_filters(db_engine):
    """Recall filters by type and related_to."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="ceo-mem",
                name="CEO",
                role="CEO",
                type="manager",
                backstory="The CEO.",
            )
        )
        await session.commit()

    with patch("opencompany.company.memory.async_session", factory):
        from opencompany.company.memory import recall_memories, store_memory

        await store_memory("ceo-mem", "fact", "Team has 5 members")
        await store_memory("ceo-mem", "decision", "Hire a designer", related_to="ticket-42")
        await store_memory("ceo-mem", "fact", "Budget is tight", related_to="ticket-42")

        # Filter by type
        facts = await recall_memories("ceo-mem", type="fact")
        assert len(facts) == 2
        assert all(m["type"] == "fact" for m in facts)

        decisions = await recall_memories("ceo-mem", type="decision")
        assert len(decisions) == 1

        # Filter by related_to
        ticket_related = await recall_memories("ceo-mem", related_to="ticket-42")
        assert len(ticket_related) == 2

        # Filter by both
        specific = await recall_memories("ceo-mem", type="fact", related_to="ticket-42")
        assert len(specific) == 1
        assert specific[0]["content"] == "Budget is tight"


async def test_build_memory_context(db_engine):
    """build_memory_context formats memories as a text block."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="pm-mem",
                name="PM",
                role="PM",
                type="manager",
                backstory="The PM.",
            )
        )
        await session.commit()

    with patch("opencompany.company.memory.async_session", factory):
        from opencompany.company.memory import build_memory_context, store_memory

        await store_memory("pm-mem", "fact", "Sprint 1 completed")
        await store_memory("pm-mem", "decision", "Prioritize backend", related_to="sprint-2")

        ctx = await build_memory_context("pm-mem")
        assert "[MEMORY" in ctx
        assert "[END MEMORY]" in ctx
        assert "Sprint 1 completed" in ctx
        assert "Prioritize backend" in ctx
        assert "(re: sprint-2)" in ctx


async def test_build_memory_context_empty(db_engine):
    """build_memory_context returns empty string when no memories exist."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="empty-mem",
                name="Empty",
                role="Dev",
                type="solver",
                backstory="No memories.",
            )
        )
        await session.commit()

    with patch("opencompany.company.memory.async_session", factory):
        from opencompany.company.memory import build_memory_context

        ctx = await build_memory_context("empty-mem")
        assert ctx == ""


async def test_compaction(db_engine):
    """Old memories are summarized when count exceeds threshold."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="compact-mem",
                name="Compact",
                role="Dev",
                type="solver",
                backstory="Will be compacted.",
            )
        )
        await session.commit()

    with patch("opencompany.company.memory.async_session", factory):
        from opencompany.company.memory import compact_memories, recall_memories, store_memory

        # Store 15 memories (threshold=10, keep=5 for test)
        for i in range(15):
            await store_memory("compact-mem", "fact", f"Memory entry {i}")

        # Before compaction
        all_before = await recall_memories("compact-mem", limit=100)
        assert len(all_before) == 15

        # Compact with low threshold
        await compact_memories("compact-mem", threshold=10, keep=5)

        # After compaction: 5 kept + 1 compacted summary = 6
        all_after = await recall_memories("compact-mem", limit=100)
        assert len(all_after) == 6

        # One should be a compacted summary
        compacted = [m for m in all_after if m["type"] == "compacted"]
        assert len(compacted) == 1
        assert "Compacted 10 older memories" in compacted[0]["content"]


async def test_compaction_below_threshold(db_engine):
    """Compaction is a no-op when memory count is below threshold."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="nocompact",
                name="NoCompact",
                role="Dev",
                type="solver",
                backstory="Below threshold.",
            )
        )
        await session.commit()

    with patch("opencompany.company.memory.async_session", factory):
        from opencompany.company.memory import compact_memories, recall_memories, store_memory

        for i in range(5):
            await store_memory("nocompact", "fact", f"Entry {i}")

        await compact_memories("nocompact", threshold=10, keep=3)

        all_mems = await recall_memories("nocompact", limit=100)
        assert len(all_mems) == 5  # unchanged


# ---------------------------------------------------------------------------
# Tool wrappers
# ---------------------------------------------------------------------------
def test_remember_tool():
    """remember tool calls store_memory via _run_async."""
    from opencompany.agents.tools.memory import remember

    with (
        patch("opencompany.company.memory.store_memory"),
        patch("opencompany.utils._run_async", side_effect=mock_run_async(42)),
    ):
        result = remember.__wrapped__(
            content="Test memory",
            memory_type="fact",
            related_to="test-ctx",
            persona_id="dev-1",
        )

    assert "42" in result
    assert "stored" in result


def test_recall_tool():
    """recall tool calls recall_memories via _run_async."""
    from opencompany.agents.tools.memory import recall

    mock_memories = [
        {"id": 1, "type": "fact", "content": "Hello world", "related_to": None},
        {"id": 2, "type": "decision", "content": "Use Python", "related_to": "tech"},
    ]

    with patch("opencompany.utils._run_async", side_effect=mock_run_async(mock_memories)):
        result = recall.__wrapped__(persona_id="dev-1")

    assert "#1" in result
    assert "Hello world" in result
    assert "#2" in result
    assert "(re: tech)" in result


def test_recall_tool_empty():
    """recall tool returns message when no memories found."""
    from opencompany.agents.tools.memory import recall

    with patch("opencompany.utils._run_async", side_effect=mock_run_async([])):
        result = recall.__wrapped__(persona_id="dev-1")

    assert "No memories" in result
