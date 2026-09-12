from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
import re

from .models import CodeEdge, CodeNode
from .parsers import ParsedFile, parse_file
from .scanner import discover_files


@dataclass(slots=True)
class IntelligenceResult:
    nodes: list[CodeNode] = field(default_factory=list)
    edges: list[CodeEdge] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)


def build_intelligence(root: str | Path) -> IntelligenceResult:
    """Build a conservative semantic model from the files CodeFlow can parse."""
    project_root = Path(root).expanduser().resolve()
    result = IntelligenceResult()
    try:
        files = discover_files(project_root)
    except ValueError as exc:
        result.diagnostics.append(str(exc))
        return result

    parsed: list[ParsedFile] = []
    for path in files:
        try:
            parsed.append(parse_file(path, project_root))
        except (OSError, UnicodeError, SyntaxError, ValueError) as exc:
            result.diagnostics.append(f"{path}: {exc}")

    result.nodes = [node for item in parsed for node in item.nodes]
    result.edges = [edge for item in parsed for edge in item.edges]
    result.edges.extend(_resolve_local_imports(parsed))
    result.edges.extend(_resolve_symbol_calls(parsed))
    return result


def _resolve_local_imports(parsed: list[ParsedFile]) -> list[CodeEdge]:
    modules: dict[str, str] = {}
    for item in parsed:
        stem = Path(item.path).stem
        modules.setdefault(stem, item.path)
        modules.setdefault(item.path.replace("/", ".").rsplit(".", 1)[0], item.path)

    edges: list[CodeEdge] = []
    seen: set[tuple[str, str]] = set()
    for item in parsed:
        for edge in item.edges:
            if edge.type != "import":
                continue
            target = modules.get(edge.target)
            if not target or target == item.path:
                continue
            key = (item.path, target)
            if key in seen:
                continue
            seen.add(key)
            edges.append(CodeEdge(source=item.path, target=target, type="dependency"))
    return edges


def _resolve_symbol_calls(parsed: list[ParsedFile]) -> list[CodeEdge]:
    """Resolve obvious same-file function calls without guessing across modules."""
    edges: list[CodeEdge] = []
    for item in parsed:
        symbols = {node.symbol for node in item.nodes if node.type in {"function", "method"}}
        if not symbols:
            continue
        for node in item.nodes:
            if node.type not in {"function", "method"} or not node.metadata:
                continue
            source_text = str(node.metadata.get("source", ""))
            for symbol in symbols:
                if symbol == node.symbol:
                    continue
                if re.search(rf"\b{re.escape(symbol)}\s*\(", source_text):
                    edges.append(CodeEdge(source=node.id, target=f"{item.path}:{symbol}", type="call"))
    return edges


def summarize(result: IntelligenceResult) -> dict[str, int]:
    counts: defaultdict[str, int] = defaultdict(int)
    for node in result.nodes:
        counts[f"node:{node.type}"] += 1
    for edge in result.edges:
        counts[f"edge:{edge.type}"] += 1
    return dict(sorted(counts.items()))
