from pathlib import Path

from analyzer.engine import analyze_project
from analyzer.models import NodeType
from analyzer.scanner import discover_files


def test_scanner_ignores_build_directories(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('ok')", encoding="utf-8")
    (tmp_path / "node_modules" / "bad.py").write_text("broken", encoding="utf-8")

    files = discover_files(tmp_path)
    assert files == [tmp_path / "src" / "main.py"]


def test_v1_analysis_has_typed_result(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("value = 1\n", encoding="utf-8")
    result = analyze_project(tmp_path)
    assert result.files_scanned == 1
    assert result.errors == []
    assert result.nodes == []
    assert NodeType.FILE.value == "file"
