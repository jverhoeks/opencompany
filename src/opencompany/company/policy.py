"""Policy documents: create, approve, reject, and inject into prompts."""

import logging

from sqlalchemy import select

from opencompany.models.db import Persona, PolicyDocument
from opencompany.models.engine import async_session

logger = logging.getLogger(__name__)


async def create_policy(
    author_id: str,
    title: str,
    content: str,
    tags: list[str] | None = None,
    applies_to: list[str] | None = None,
) -> int:
    """Create a draft policy document. Returns the policy ID."""
    async with async_session() as session:
        policy = PolicyDocument(
            title=title,
            content=content,
            author_id=author_id,
            tags=tags or [],
            applies_to=applies_to or [],
        )
        session.add(policy)
        await session.commit()
        await session.refresh(policy)
        logger.info("Created policy #%d '%s' by %s", policy.id, title, author_id)
        return policy.id


async def approve_policy(policy_id: int, approver_id: str) -> dict:
    """Approve a draft policy. Approver must be a manager or lead."""
    async with async_session() as session:
        # Validate approver is manager or lead
        approver = await session.get(Persona, approver_id)
        if not approver or approver.type not in ("manager", "lead"):
            raise PermissionError(
                f"Only managers and leads can approve policies (got {approver_id})"
            )

        policy = await session.get(PolicyDocument, policy_id)
        if not policy:
            raise ValueError(f"Policy #{policy_id} not found")
        if policy.status != "draft":
            raise ValueError(f"Policy #{policy_id} is '{policy.status}', not draft")

        policy.status = "approved"
        policy.approved_by = approver_id
        await session.commit()
        logger.info("Policy #%d approved by %s", policy_id, approver_id)
        return _policy_to_dict(policy)


async def reject_policy(policy_id: int, rejector_id: str, reason: str = "") -> dict:
    """Reject a draft policy. Rejector must be a manager or lead."""
    async with async_session() as session:
        rejector = await session.get(Persona, rejector_id)
        if not rejector or rejector.type not in ("manager", "lead"):
            raise PermissionError(
                f"Only managers and leads can reject policies (got {rejector_id})"
            )

        policy = await session.get(PolicyDocument, policy_id)
        if not policy:
            raise ValueError(f"Policy #{policy_id} not found")
        if policy.status != "draft":
            raise ValueError(f"Policy #{policy_id} is '{policy.status}', not draft")

        policy.status = "rejected"
        policy.approved_by = rejector_id  # tracks who rejected
        await session.commit()
        logger.info("Policy #%d rejected by %s: %s", policy_id, rejector_id, reason)
        return _policy_to_dict(policy)


async def list_policies(
    status: str | None = None,
    tag: str | None = None,
) -> list[dict]:
    """List policies with optional filters."""
    async with async_session() as session:
        q = select(PolicyDocument).order_by(PolicyDocument.created_at.desc())
        if status:
            q = q.where(PolicyDocument.status == status)
        result = await session.execute(q)
        policies = result.scalars().all()

        if tag:
            policies = [p for p in policies if tag in p.tags]

        return [_policy_to_dict(p) for p in policies]


async def get_policy(policy_id: int) -> dict | None:
    """Get a single policy by ID."""
    async with async_session() as session:
        policy = await session.get(PolicyDocument, policy_id)
        if not policy:
            return None
        return _policy_to_dict(policy)


async def build_policy_context(persona: Persona) -> str:
    """Build formatted policy text for injection into a persona's system prompt.

    Only approved policies that are relevant to this persona are included.
    Relevance: applies_to contains "*", persona's role, persona's ID,
    or tags overlap with persona's skills.
    """
    async with async_session() as session:
        q = select(PolicyDocument).where(PolicyDocument.status == "approved")
        result = await session.execute(q)
        all_policies = result.scalars().all()

    if not all_policies:
        return ""

    persona_skills = set(persona.skills or [])
    relevant = []
    for p in all_policies:
        applies = p.applies_to or []
        tags = set(p.tags or [])
        if (
            "*" in applies
            or persona.role in applies
            or persona.id in applies
            or tags & persona_skills
        ):
            relevant.append(p)

    if not relevant:
        return ""

    lines = ["[COMPANY POLICIES]"]
    for p in relevant:
        lines.append(f"\n### {p.title}")
        lines.append(f"(approved by {p.approved_by} | tags: {', '.join(p.tags)})")
        lines.append(p.content)
    lines.append("\n[END POLICIES]")
    return "\n".join(lines)


def _policy_to_dict(policy: PolicyDocument) -> dict:
    return {
        "id": policy.id,
        "title": policy.title,
        "content": policy.content,
        "author_id": policy.author_id,
        "status": policy.status,
        "approved_by": policy.approved_by,
        "tags": policy.tags,
        "applies_to": policy.applies_to,
        "version": policy.version,
        "created_at": policy.created_at.isoformat() if policy.created_at else None,
        "updated_at": policy.updated_at.isoformat() if policy.updated_at else None,
    }
