from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

from .models import CodeEdge, CodeNode, EdgeType, NodeType

_JS_FUNCTION = re.compile(r"\b(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(")
_JS_ARROW = re.compile(r"\b(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>")
_JS_CLASS = re.compile(r"\b(?:export\s+)?class\s+([A-Za-z_$][\w$]*)\b")
_JS_IMPORT = re.compile(r"\bimport\s+(?:[^;]*?\s+from\s+)?[\"']([^\"']+)[\"']")
_JS_REQUIRE = re.compile(r"\brequire\(\s*[\"']([^\"']+)[\"']\s*\)")


@dataclass(frozen=True)
class ParsedFile:
    nodes: list[CodeNode]
    edges: list[CodeEdge]


def _node_id(relative: str, kind: str, name: str) -> str:
    return f"{relative}::{kind}::{name}"


def _python(path: Path, root: Path, source: str) -> ParsedFile:
    tree = ast.parse(source, filename=str(path))
    relative = path.relative_to(root).as_posix()
    file_id = _node_id(relative, "file", relative)
    nodes = [CodeNode(id=file_id, type=NodeType.FILE, symbol=relative, file=relative, line=1, end_line=max(1, len(source.splitlines())), language="python")]
    edges: list[CodeEdge] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.scope: list[str] = []

        def _add_symbol(self, node: ast.AST, name: str, kind: NodeType) -> None:
            line = getattr(node, "lineno", 1)
            end_line = getattr(node, "end_lineno", line)
            node_id = _node_id(relative, kind.value, name)
            nodes.append(CodeNode(id=node_id, type=kind, symbol=name, file=relative, line=line, end_line=end_line, language="python"))
            parent = _node_id(relative, NodeType.FUNCTION.value, self.scope[-1]) if self.scope else file_id
            edges.append(CodeEdge(source=parent, target=node_id, type=EdgeType.CONTAINS))

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            self._add_symbol(node, node.name, NodeType.CLASS)
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            kind = NodeType.METHOD if self.scope else NodeType.FUNCTION
            self._add_symbol(node, node.name, kind)
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def _add_import(self, node: ast.AST, module: str) -> None:
            line = getattr(node, "lineno", 1)
            import_id = _node_id(relative, NodeType.IMPORT.value, module)
            nodes.append(CodeNode(id=import_id, type=NodeType.IMPORT, symbol=module, file=relative, line=line, end_line=line, language="python"))
            edges.append(CodeEdge(source=file_id, target=import_id, type=EdgeType.IMPORTS, label=module))

        def visit_Import(self, node: ast.Import) -> None:
            for alias in node.names:
                self._add_import(node, alias.name)

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            self._add_import(node, "." * node.level + (node.module or ""))

    Visitor().visit(tree)
    return ParsedFile(nodes, edges)


def _javascript(path: Path, root: Path, source: str) -> ParsedFile:
    relative = path.relative_to(root).as_posix()
    language = "typescript" if path.suffix in {".ts", ".tsx"} else "javascript"
    lines = source.splitlines()
    file_id = _node_id(relative, "file", relative)
    nodes = [CodeNode(id=file_id, type=NodeType.FILE, symbol=relative, file=relative, line=1, end_line=max(1, len(lines)), language=language)]
    edges: list[CodeEdge] = []

    declarations: list[tuple[str, NodeType, int]] = []
    for pattern, kind in ((_JS_CLASS, NodeType.CLASS), (_JS_FUNCTION, NodeType.FUNCTION), (_JS_ARROW, NodeType.FUNCTION)):
        for match in pattern.finditer(source):
            line = source.count("\n", 0, match.start()) + 1
            declarations.append((match.group(1), kind, line))

    seen: set[str] = set()
    for name, kind, line in sorted(declarations, key=lambda item: item[2]):
        key = f"{kind.value}:{name}"
        if key in seen:
            continue
        seen.add(key)
        node_id = _node_id(relative, kind.value, name)
        nodes.append(CodeNode(id=node_id, type=kind, symbol=name, file=relative, line=line, end_line=line, language=language))
        edges.append(CodeEdge(source=file_id, target=node_id, type=EdgeType.CONTAINS))

    imports = _JS_IMPORT.findall(source) + _JS_REQUIRE.findall(source)
    for module in dict.fromkeys(imports):
        import_id = _node_id(relative, NodeType.IMPORT.value, module)
        match = re.search(re.escape(module), source)
        line = source.count("\n", 0, match.start()) + 1 if match else 1
        nodes.append(CodeNode(id=import_id, type=NodeType.IMPORT, symbol=module, file=relative, line=line, end_line=line, language=language))
        edges.append(CodeEdge(source=file_id, target=import_id, type=EdgeType.IMPORTS, label=module, confidence=0.9))

    return ParsedFile(nodes, edges)


def parse_file(path: Path, root: Path) -> ParsedFile:
    source = path.read_text(encoding="utf-8")
    if path.suffix == ".py":
        return _python(path, root, source)
    if path.suffix in {".js", ".jsx", ".ts", ".tsx"}:
        return _javascript(path, root, source)
    raise ValueError(f"Unsupported source language: {path.suffix}")
