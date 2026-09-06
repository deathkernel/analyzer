from pathlib import Path
from tempfile import TemporaryDirectory

from scanner import analyze, import_tokens
from graph_engine import build_graph

def test_scanner_deduplicates_password_findings():
    with TemporaryDirectory() as tmp:
        root=Path(tmp)
        (root/"main.py").write_text('password = "supersecret123"\nprint(password)\n',encoding="utf-8")
        result=analyze(root)
        findings=[x for x in result["issues"] if x["file"]=="main.py"]
        assert [x["type"] for x in findings].count("SECRET")==1
        assert [x["type"] for x in findings].count("PASSWORD_LITERAL")==0

def test_scanner_finds_literal_div_zero():
    with TemporaryDirectory() as tmp:
        root=Path(tmp)
        (root/"main.py").write_text("value = 4 / 0\n",encoding="utf-8")
        result=analyze(root)
        assert any(x["type"]=="DIV_ZERO" and x["severity"]=="CRITICAL" for x in result["issues"])

def test_graph_prefers_exact_module_path():
    with TemporaryDirectory() as tmp:
        root=Path(tmp)
        (root/"pkg").mkdir()
        (root/"pkg"/"alpha.py").write_text("x = 1\n",encoding="utf-8")
        (root/"other").mkdir()
        (root/"other"/"alpha.py").write_text("x = 2\n",encoding="utf-8")
        (root/"main.py").write_text("from pkg import alpha\nprint(alpha.x)\n",encoding="utf-8")
        files=[p for p in root.rglob("*.py")]
        contents={p:p.read_text(encoding="utf-8") for p in files}
        nodes,edges=build_graph(root,files,contents)
        main_id="@file:main.py"
        target_ids={e["target"] for e in edges if e["source"]==main_id and e["kind"]=="import"}
        assert "@file:pkg/alpha.py" in target_ids

def test_import_tokens_are_stable():
    tokens=import_tokens("import os\nfrom pkg import alpha\n",Path("main.py"))
    assert tokens==["os","pkg"]
