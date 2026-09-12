from __future__ import annotations

from pathlib import Path

from .models import AnalysisResult
from .parsers import parse_file
from .scanner import discover_files


def analyze_project(root: str | Path) -> AnalysisResult:
    project_root = Path(root).expanduser().resolve()
    result = AnalysisResult(root=str(project_root))
    try:
        files = discover_files(project_root)
    except ValueError as exc:
        result.errors.append(str(exc))
        return result

    result.files_scanned = len(files)
    for path in files:
        try:
            parsed = parse_file(path, project_root)
            result.nodes.extend(parsed.nodes)
            result.edges.extend(parsed.edges)
        except (OSError, UnicodeError, SyntaxError, ValueError) as exc:
            result.errors.append(f"{path.relative_to(project_root)}: {exc}")
    return result
