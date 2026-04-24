"""Task board: ticket lifecycle, auto-assignment, sync wrappers for tool use."""

import logging
import random
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select, update

from opencompany.events.bus import publish
from opencompany.models.db import Persona, Ticket, WorkLog
from opencompany.models.engine import async_session
from opencompany.utils import _run_async

logger = logging.getLogger(__name__)


def _fuzzy_tag_score(solver_tags: set[str], ticket_tags: set[str]) -> float:
    """Score a solver against ticket tags using exact + length-weighted substring.

    - Exact match: ``1.0`` per ticket tag.
    - Substring match: ``0.5 × (shorter_len / longer_len)``, taking the best
      partial across all solver tags (not summed — one ticket tag, one
      partial credit).

    The length-weighting stops broad generic tags from dominating specialised
    tickets. Example: a solver with ``picks_up=["dev"]`` used to score 0.5 on
    every ``*-dev`` ticket (equal to a specialist's full substring match),
    which let catch-all generalists outscore focused specialists on tickets
    the specialists were hired to own. With weighting, ``"dev"`` (len 3) on
    ``"frontend-dev"`` (len 12) scores only ``0.5 × 3/12 = 0.125`` — a specialist
    with exact-match on ``"frontend-dev"`` still wins 1.0 vs 0.125.

    We also bound credit to the *best* partial per ticket tag, so a solver
    with many redundant variants of the same tag can't stack partial credit.
    """
    score = 0.0
    for tt in ticket_tags:
        if tt in solver_tags:
            score += 1.0
            continue
        best_partial = 0.0
        for st in solver_tags:
            if st == tt:
                # Unreachable via the ``tt in solver_tags`` fast-path, but
                # defensively handle zero-length pathologies below.
                continue
            if not st or not tt:
                continue
            if st in tt:
                ratio = len(st) / len(tt)
                best_partial = max(best_partial, 0.5 * ratio)
            elif tt in st:
                ratio = len(tt) / len(st)
                best_partial = max(best_partial, 0.5 * ratio)
        score += best_partial
    return score


def find_best_solver(tags: list[str], solvers: list[dict]) -> dict | None:
    """Find the best-matched solver for a ticket.

    Returns the highest-scoring solver (score > 0) by skill overlap, with
    workload as a tiebreaker. Returns ``None`` when no solver has a
    positive tag-match score — this lets the caller escalate the ticket
    to the CEO rather than blindly dumping a ``["blockchain"]`` ticket on
    the least-busy Python specialist. A "least-busy fallback" at this
    layer was a silent correctness bug: the escalation path in
    ``_assign_to_solver`` only fired on an empty solver pool, which
    almost never happens in practice.
    """
    if not solvers:
        return None

    ticket_tags = {t.lower() for t in tags}
    candidates = []
    for solver in solvers:
        solver_tags = {s.lower() for s in solver["skills"]}
        score = _fuzzy_tag_score(solver_tags, ticket_tags)
        logger.debug(
            "Solver scoring: %s score=%.2f workload=%d (skills=%s vs tags=%s)",
            solver["id"],
            score,
            solver["workload"],
            solver["skills"],
            tags,
        )
        if score > 0:
            candidates.append((score, solver["workload"], solver))

    if not candidates:
        logger.info("No tag match for %s — caller should escalate", tags)
        return None

    # Sort by score (desc), workload (asc), random tiebreaker. Without
    # the random factor, the same solver always wins when tied.
    candidates.sort(key=lambda x: (-x[0], x[1], random.random()))
    best = candidates[0]
    logger.info(
        "Best solver: %s (score=%.2f, workload=%d, %d candidates)",
        best[2]["id"],
        best[0],
        best[1],
        len(candidates),
    )
    return best[2]


async def _create_ticket(
    title: str,
    description: str,
    priority: str,
    tags: list,
    context: dict,
    created_by: str,
) -> int:
    async with async_session() as session:
        ticket = Ticket(
            title=title,
            description=description,
            priority=priority,
            tags=tags,
            context=context,
            created_by=created_by,
        )
        session.add(ticket)
        log = WorkLog(persona_id=created_by, action="created", ticket_id=ticket.id)
        session.add(log)
        await session.commit()
        await session.refresh(ticket)
        await publish("ticket.created", {"ticket_id": ticket.id})
        logger.info(
            "Created ticket %d: %s (priority=%s, by=%s)",
            ticket.id,
            title,
            priority,
            created_by,
        )
        return ticket.id


def create_ticket_sync(**kwargs) -> int:
    """Sync wrapper for use in @tool functions."""
    return _run_async(_create_ticket(**kwargs))


async def _list_tickets(status: str, tags: list) -> list[dict]:
    async with async_session() as session:
        q = select(Ticket).where(Ticket.status == status)
        result = await session.execute(q)
        tickets = result.scalars().all()
        if tags:
            tickets = [t for t in tickets if set(tags) & set(t.tags)]
        logger.debug("Listed %d tickets (status=%s, tags=%s)", len(tickets), status, tags)
        return [
            {
                "id": t.id,
                "title": t.title,
                "priority": t.priority,
                "assigned_to": t.assigned_to,
                "tags": t.tags,
            }
            for t in tickets
        ]


def list_tickets_sync(**kwargs) -> list[dict]:
    return _run_async(_list_tickets(**kwargs))


async def _update_ticket(ticket_id: int, status: str | None = None, result: str | None = None):
    async with async_session() as session:
        ticket = await session.get(Ticket, ticket_id)
        if not ticket:
            logger.warning("Ticket #%d not found for update", ticket_id)
            return f"Error: ticket #{ticket_id} not found"
        if status:
            ticket.status = status
            log = WorkLog(
                persona_id=ticket.created_by or "system",
                action=status,
                ticket_id=ticket_id,
            )
            session.add(log)
        if result:
            ticket.result = result
        ticket.updated_at = datetime.now(UTC)
        await session.commit()
        logger.info("Updated ticket %d (status=%s)", ticket_id, status)

        # Trigger review flow when a solver submits for review
        if status == "review":
            await publish("ticket.review", {"ticket_id": ticket_id})


def update_ticket_sync(**kwargs):
    return _run_async(_update_ticket(**kwargs))


# Minimum token gap for a peer to be considered "notably lighter" than
# the claimer. Small enough to engage the fairness back-off during a
# busy day, large enough to avoid thrashing around rounding noise.
_FAIRNESS_MARGIN_TOKENS = 500


def _has_lighter_peer_for(
    ticket: Ticket,
    peers: Sequence[Persona],
    claimer_score: float,
    claimer_tokens: int,
) -> bool:
    """Return ``True`` if a peer solver is equally-or-better matched AND less loaded.

    "Less loaded" uses ``tokens_used_today`` with a ``_FAIRNESS_MARGIN_TOKENS``
    threshold — a peer merely a few tokens behind doesn't trigger back-off.
    Only invoked from ``claim_next`` so we can defer a claim to let the
    lighter peer pick the ticket up via the periodic sweep or their own
    idle event. Without this, a fast solver drains the queue while equal
    peers idle, even though the push-path (``_assign_to_solver``) is
    workload-aware — the pull path bypassed it.
    """
    ticket_tags = {t.lower() for t in ticket.tags}
    for peer in peers:
        peer_tags = {s.lower() for s in (peer.picks_up or peer.skills or [])}
        if not peer_tags:
            continue
        peer_score = _fuzzy_tag_score(peer_tags, ticket_tags)
        if peer_score < claimer_score:
            continue
        peer_tokens = peer.tokens_used_today or 0
        if peer_tokens + _FAIRNESS_MARGIN_TOKENS < claimer_tokens:
            return True
    return False


async def claim_next(persona_id: str) -> dict | None:
    """Atomically claim the best open ticket for a persona.

    Uses tag-based matching (picks_up / skills) to find the best fit, then
    applies a fairness back-off: if a peer with equal-or-better match is
    notably less loaded, skip this ticket and let them pick it up via the
    sweep or their own idle event. Prevents a fast solver from
    monopolising the queue while equal peers sit idle.

    Returns a dict with ticket info if claimed, ``None`` otherwise.
    """
    async with async_session() as session:
        persona = await session.get(Persona, persona_id)
        if not persona or persona.status != "active":
            return None

        picks_up = persona.picks_up or persona.skills or []
        if not picks_up:
            return None

        # Fetch peer solvers once for fairness comparison. Small teams make
        # this a handful of rows — no need for a smarter query shape.
        peer_stmt = select(Persona).where(
            Persona.type == "solver",
            Persona.status == "active",
            Persona.id != persona_id,
        )
        peers = (await session.execute(peer_stmt)).scalars().all()

        result = await session.execute(
            select(Ticket).where(
                Ticket.status == "open",
                Ticket.assigned_to.is_(None),
            )
        )
        candidates = result.scalars().all()
        if not candidates:
            return None

        # Score candidates by tag match — iterate by score descending so we
        # can try to claim the best, and fall through to the next-best if
        # another persona beat us to the row between scoring and UPDATE.
        persona_tags = {s.lower() for s in picks_up}
        scored: list[tuple[float, Ticket]] = []
        for ticket in candidates:
            ticket_tags = {t.lower() for t in ticket.tags}
            score = _fuzzy_tag_score(persona_tags, ticket_tags)
            if score > 0:
                scored.append((score, ticket))
        scored.sort(key=lambda p: (-p[0], p[1].id))

        claimer_tokens = persona.tokens_used_today or 0

        # Conditional UPDATE: only update if the row is still unassigned and
        # status still open. Rowcount tells us whether we actually won the
        # race — this works on Postgres and SQLite alike without needing
        # SELECT ... FOR UPDATE SKIP LOCKED (which SQLite doesn't support).
        for score, ticket in scored:
            if _has_lighter_peer_for(ticket, peers, score, claimer_tokens):
                logger.debug(
                    "Persona %s backing off ticket #%d (lighter peer available)",
                    persona_id,
                    ticket.id,
                )
                continue

            update_stmt = (
                update(Ticket)
                .where(
                    Ticket.id == ticket.id,
                    Ticket.status == "open",
                    Ticket.assigned_to.is_(None),
                )
                .values(
                    status="assigned",
                    assigned_to=persona_id,
                    updated_at=datetime.now(UTC),
                )
            )
            upd = await session.execute(update_stmt)
            if upd.rowcount != 1:
                # Another persona claimed this one — try the next best.
                continue

            session.add(WorkLog(persona_id=persona_id, action="claimed", ticket_id=ticket.id))
            await session.commit()

            logger.info(
                "Persona %s claimed ticket #%d (score=%.2f)",
                persona_id,
                ticket.id,
                score,
            )
            return {
                "id": ticket.id,
                "title": ticket.title,
                "description": ticket.description,
                "tags": ticket.tags,
                "priority": ticket.priority,
            }

        return None
