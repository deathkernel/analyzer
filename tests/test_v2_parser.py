from pathlib import Path

from analyzer.parsers import parse_file
from analyzer.models import EdgeType, NodeType


def test_python_parser_extracts_symbols_and_imports(tmp_path: Path) -> None:
    source = "import json\n\nclass Service:\n    def run(self):\n        return json.dumps({})\n\ndef helper():\n    return 1\n"
    path = tmp_path / "service.py"
    path.write_text(source, encoding="utf-8")

    result = parse_file(path, tmp_path)
    symbols = {(node.type, node.symbol) for node in result.nodes}

    assert (NodeType.CLASS, "Service") in symbols
    assert (NodeType.METHOD, "run") in symbols
    assert (NodeType.FUNCTION, "helper") in symbols
    assert (NodeType.IMPORT, "json") in symbols
    assert any(edge.type is EdgeType.IMPORTS for edge in result.edges)
    assert any(edge.type is EdgeType.CONTAINS for edge in result.edges)


def test_typescript_parser_extracts_functions_classes_and_imports(tmp_path: Path) -> None:
    source = "import React from 'react';\n\nexport class App {}\nexport const boot = () => App;\nfunction start() {}\n"
    path = tmp_path / "app.tsx"
    path.write_text(source, encoding="utf-8")

    result = parse_file(path, tmp_path)
    symbols = {(node.type, node.symbol) for node in result.nodes}

    assert (NodeType.CLASS, "App") in symbols
    assert (NodeType.FUNCTION, "boot") in symbols
    assert (NodeType.FUNCTION, "start") in symbols
    assert (NodeType.IMPORT, "react") in symbols


def test_python_syntax_errors_are_not_silently_accepted(tmp_path: Path) -> None:
    path = tmp_path / "broken.py"
    path.write_text("def broken(:\n", encoding="utf-8")

    try:
        parse_file(path, tmp_path)
    except SyntaxError:
        pass
    else:
        raise AssertionError("invalid Python should raise SyntaxError")
