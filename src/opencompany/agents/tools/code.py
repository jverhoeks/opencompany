import os
import subprocess

from strands import tool


@tool
def read_file(path: str) -> str:
    """Read the contents of a file.

    Args:
        path: Path to the file to read
    """
    if not os.path.isfile(path):
        return f"Error: {path} not found"
    with open(path) as f:
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
        result = subprocess.run(
            ["grep", "-rn", "--include", file_glob, pattern, directory],
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

    if pattern:
        files = glob_mod.glob(os.path.join(directory, pattern), recursive=True)
    else:
        files = os.listdir(directory)
    return "\n".join(sorted(files)[:100])
