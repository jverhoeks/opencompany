from opencompany.models.db import Persona, Ticket, WorkLog


def test_persona_creation():
    p = Persona(
        id="security-analyst",
        name="Sarah Chen",
        role="Security Analyst",
        type="observer",
        skills=["security", "code-review"],
        backstory="Senior security engineer.",
        status="active",
    )
    assert p.id == "security-analyst"
    assert p.type == "observer"
    assert "security" in p.skills


def test_ticket_creation():
    t = Ticket(
        title="SQL injection in auth.py",
        priority="critical",
        status="open",
        tags=["security", "backend"],
        created_by="security-analyst",
    )
    assert t.status == "open"
    assert t.priority == "critical"


def test_persona_defaults():
    p = Persona(
        id="test",
        name="Test",
        role="Test",
        type="solver",
    )
    assert p.skills == []
    assert p.status == "active"
    assert p.backstory == ""


def test_work_log_creation():
    w = WorkLog(
        persona_id="security-analyst",
        action="created",
        details="Created ticket for SQL injection",
    )
    assert w.action == "created"
    assert w.ticket_id is None
