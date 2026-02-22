"""Tests for private & shared workspace routing and publish_file."""

from unittest.mock import patch


def test_persona_writes_to_private_workspace(tmp_path):
    """write_file with persona_id writes to private/{persona_id}/."""
    from opencompany.agents.tools.code import write_file

    with patch("opencompany.agents.tools.code.WORKSPACE_ROOT", str(tmp_path)):
        result = write_file.__wrapped__(
            path="hello.py",
            content="print('hello')",
            persona_id="backend-dev",
        )

    assert "Wrote" in result
    private_file = tmp_path / "private" / "backend-dev" / "hello.py"
    assert private_file.exists()
    assert private_file.read_text() == "print('hello')"


def test_persona_reads_shared_workspace(tmp_path):
    """read_file with shared/ prefix reads from shared workspace."""
    from opencompany.agents.tools.code import read_file

    shared = tmp_path / "shared"
    shared.mkdir(parents=True)
    (shared / "notes.md").write_text("# Shared notes")

    with patch("opencompany.agents.tools.code.WORKSPACE_ROOT", str(tmp_path)):
        result = read_file.__wrapped__(path="shared/notes.md", persona_id="backend-dev")

    assert "# Shared notes" in result


def test_publish_file_copies_to_shared(tmp_path):
    """publish_file copies a file from private to shared."""
    from opencompany.agents.tools.code import publish_file

    private = tmp_path / "private" / "frontend-dev"
    private.mkdir(parents=True)
    (private / "index.html").write_text("<h1>Landing Page</h1>")

    with patch("opencompany.agents.tools.code.WORKSPACE_ROOT", str(tmp_path)):
        result = publish_file.__wrapped__(
            source_path="index.html",
            persona_id="frontend-dev",
        )

    assert "Published" in result
    shared_file = tmp_path / "shared" / "index.html"
    assert shared_file.exists()
    assert "<h1>Landing Page</h1>" in shared_file.read_text()


def test_workspace_path_escape_blocked(tmp_path):
    """Path traversal (../) is rejected."""
    from opencompany.agents.tools.code import read_file, write_file

    with patch("opencompany.agents.tools.code.WORKSPACE_ROOT", str(tmp_path)):
        result = read_file.__wrapped__(path="../../etc/passwd", persona_id="backend-dev")
        assert "Error" in result

        result = write_file.__wrapped__(
            path="../../../tmp/evil.py",
            content="bad",
            persona_id="backend-dev",
        )
        assert "Error" in result


def test_publish_file_requires_persona_id(tmp_path):
    """publish_file without persona_id returns an error."""
    from opencompany.agents.tools.code import publish_file

    with patch("opencompany.agents.tools.code.WORKSPACE_ROOT", str(tmp_path)):
        result = publish_file.__wrapped__(source_path="file.txt", persona_id="")

    assert "Error" in result


def test_publish_file_missing_source(tmp_path):
    """publish_file returns error when source file doesn't exist."""
    from opencompany.agents.tools.code import publish_file

    (tmp_path / "private" / "dev").mkdir(parents=True)

    with patch("opencompany.agents.tools.code.WORKSPACE_ROOT", str(tmp_path)):
        result = publish_file.__wrapped__(source_path="nonexistent.py", persona_id="dev")

    assert "not found" in result


def test_default_workspace_still_works(tmp_path):
    """Tools without persona_id still work against WORKSPACE_ROOT."""
    from opencompany.agents.tools.code import write_file

    with patch("opencompany.agents.tools.code.WORKSPACE_ROOT", str(tmp_path)):
        result = write_file.__wrapped__(path=str(tmp_path / "test.py"), content="ok")

    assert "Wrote" in result
    assert (tmp_path / "test.py").read_text() == "ok"
