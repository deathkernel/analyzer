from __future__ import annotations

from pathlib import Path

IGNORED_DIRS = {".git", ".venv", "venv", "node_modules", "dist", "build", "__pycache__", ".pytest_cache"}
SUPPORTED_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx"}


def discover_files(root: Path) -> list[Path]:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"Project root is not a directory: {root}")

    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        files.append(path)
    return sorted(files)
