import os
import subprocess

from strands import tool

WORKSPACE_ROOT = os.path.realpath(os.environ.get("WORKSPACE_ROOT", "workspaces"))


def _safe_resolve(path: str, base: str = WORKSPACE_ROOT) -> str:
    """Resolve *path* and verify it lives inside *base*.

    Raises ``ValueError`` if the resolved path escapes the base directory.
    """
    resolved = os.path.realpath(path)
    base = os.path.realpath(base)
    if not (resolved == base or resolved.startswith(base + os.sep)):
        raise ValueError(f"Path {path!r} resolves outside the allowed workspace")
    return resolved


@tool
def read_file(path: str) -> str:
    """Read the contents of a file.

    Args:
        path: Path to the file to read
    """
    try:
        safe = _safe_resolve(path)
    except ValueError as e:
        return f"Error: {e}"
    if not os.path.isfile(safe):
        return f"Error: {path} not found"
    with open(safe) as f:
        return f.read()


@tool
def grep_code(pattern: str, directory: str = ".", file_glob: str = "*.py") -> str:
    """Search for a pattern in code files.

    Args:
        pattern: Regex pattern to search for
        directory: Directory to search in
        file_glob: File glob pattern to match (e.g. *.py, *.yaml)
    """
    try:
        safe_dir = _safe_resolve(directory)
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
def list_files(directory: str = ".", pattern: str = "") -> str:
    """List files in a directory.

    Args:
        directory: Directory to list
        pattern: Optional glob pattern to filter files
    """
    import glob as glob_mod

    try:
        safe_dir = _safe_resolve(directory)
    except ValueError as e:
        return f"Error: {e}"
    if pattern:
        files = glob_mod.glob(os.path.join(safe_dir, pattern), recursive=True)
    else:
        files = os.listdir(safe_dir)
    return "\n".join(sorted(files)[:100])
