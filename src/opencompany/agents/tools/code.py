import logging
import os
import shutil
import subprocess

from strands import tool

logger = logging.getLogger(__name__)

WORKSPACE_ROOT = os.path.realpath(os.environ.get("WORKSPACE_ROOT", "workspaces"))


def _persona_workspace(persona_id: str) -> str:
    """Return path to persona's private workspace."""
    return os.path.join(WORKSPACE_ROOT, "private", persona_id)


def _shared_workspace() -> str:
    """Return path to shared workspace."""
    return os.path.join(WORKSPACE_ROOT, "shared")


def _resolve_workspace_path(path: str, persona_id: str = "") -> str:
    """Resolve a path against the appropriate workspace.

    - Paths starting with ``shared/`` resolve against the shared workspace.
    - When *persona_id* is given, other paths resolve against that persona's
      private workspace.
    - Otherwise falls back to the global WORKSPACE_ROOT.

    Always sandboxed under WORKSPACE_ROOT.
    """
    if path.startswith("shared/") or path.startswith("shared" + os.sep):
        base = _shared_workspace()
        rel = path[len("shared/") :]
        full = os.path.join(base, rel)
    elif persona_id:
        base = _persona_workspace(persona_id)
        full = os.path.join(base, path)
    else:
        full = path
        base = WORKSPACE_ROOT
    return _safe_resolve(full, WORKSPACE_ROOT)


def _safe_resolve(path: str, base: str | None = None) -> str:
    """Resolve *path* and verify it lives inside *base*.

    Raises ``ValueError`` if the resolved path escapes the base directory.
    """
    if base is None:
        base = WORKSPACE_ROOT
    resolved = os.path.realpath(path)
    base = os.path.realpath(base)
    if not (resolved == base or resolved.startswith(base + os.sep)):
        raise ValueError(f"Path {path!r} resolves outside the allowed workspace")
    return resolved


@tool
def read_file(path: str, persona_id: str = "") -> str:
    """Read the contents of a file.

    Args:
        path: Path to the file to read
        persona_id: Your persona ID (injected by the system)
    """
    try:
        safe = _resolve_workspace_path(path, persona_id)
    except ValueError as e:
        return f"Error: {e}"
    if not os.path.isfile(safe):
        return f"Error: {path} not found"
    with open(safe) as f:
        return f.read()


@tool
def grep_code(
    pattern: str, directory: str = ".", file_glob: str = "*.py", persona_id: str = ""
) -> str:
    """Search for a pattern in code files.

    Args:
        pattern: Regex pattern to search for
        directory: Directory to search in
        file_glob: File glob pattern to match (e.g. *.py, *.yaml)
        persona_id: Your persona ID (injected by the system)
    """
    try:
        safe_dir = _resolve_workspace_path(directory, persona_id)
    except ValueError as e:
        return f"Error: {e}"
    try:
        result = subprocess.run(
            ["grep", "-rn", "--include", file_glob, pattern, safe_dir],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout[:5000] if result.stdout else "No matches found"
    except Exception as e:
        return f"Error: {e}"


@tool
def write_file(path: str, content: str, persona_id: str = "") -> str:
    """Write content to a file in the workspace. Creates parent directories as needed.

    Args:
        path: Path to the file to write (relative to workspace root)
        content: Content to write to the file
        persona_id: Your persona ID (injected by the system)
    """
    try:
        safe = _resolve_workspace_path(path, persona_id)
    except ValueError as e:
        return f"Error: {e}"
    os.makedirs(os.path.dirname(safe), exist_ok=True)
    with open(safe, "w") as f:
        f.write(content)
    logger.info("[%s] write_file: %s (%d bytes)", persona_id or "?", path, len(content))
    return f"Wrote {len(content)} bytes to {path}"


@tool
def list_files(directory: str = ".", pattern: str = "", persona_id: str = "") -> str:
    """List files in a directory.

    Args:
        directory: Directory to list
        pattern: Optional glob pattern to filter files
        persona_id: Your persona ID (injected by the system)
    """
    import glob as glob_mod

    try:
        safe_dir = _resolve_workspace_path(directory, persona_id)
    except ValueError as e:
        return f"Error: {e}"
    if pattern:
        files = glob_mod.glob(os.path.join(safe_dir, pattern), recursive=True)
    else:
        files = os.listdir(safe_dir)
    return "\n".join(sorted(files)[:100])


@tool
def publish_file(source_path: str, persona_id: str = "") -> str:
    """Copy a file from your private workspace to the shared workspace.

    Args:
        source_path: Path in your private workspace to publish
        persona_id: Your persona ID (injected by the system)
    """
    if not persona_id:
        return "Error: persona_id is required to publish files"
    private = _persona_workspace(persona_id)
    src = os.path.join(private, source_path)
    try:
        src = _safe_resolve(src, WORKSPACE_ROOT)
    except ValueError as e:
        return f"Error: {e}"
    if not os.path.isfile(src):
        return f"Error: {source_path} not found in your workspace"
    shared = _shared_workspace()
    os.makedirs(shared, exist_ok=True)
    dest = os.path.join(shared, os.path.basename(source_path))
    shutil.copy2(src, dest)
    dest_name = os.path.basename(source_path)
    logger.info("[%s] publish_file: %s → shared/%s", persona_id, source_path, dest_name)
    return f"Published {source_path} to shared/{os.path.basename(source_path)}"
