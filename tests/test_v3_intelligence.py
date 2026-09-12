from pathlib import Path

from analyzer.intelligence import build_intelligence, summarize


def test_v3_resolves_local_import_and_same_file_call(tmp_path: Path) -> None:
    (tmp_path / "helpers.py").write_text("def helper():\n    return 1\n")
    (tmp_path / "main.py").write_text(
        "import helpers\n\ndef run():\n    return finish()\n\ndef finish():\n    return 2\n"
    )

    result = build_intelligence(tmp_path)

    assert any(edge.type == "dependency" and edge.target == "helpers.py" for edge in result.edges)
    assert any(edge.type == "call" and edge.target == "main.py:finish" for edge in result.edges)
    assert not result.diagnostics


def test_v3_summary_counts_nodes_and_edges(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("def run():\n    return 1\n")

    result = build_intelligence(tmp_path)
    summary = summarize(result)

    assert summary["node:function"] == 1
