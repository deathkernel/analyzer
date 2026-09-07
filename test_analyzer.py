from pathlib import Path
from tempfile import TemporaryDirectory

from scanner import analyze, import_tokens
from graph_engine import build_graph
from exception_engine import analyze_exceptions


def test_scanner_deduplicates_password_findings():
    with TemporaryDirectory() as tmp:
        root=Path(tmp);(root/"main.py").write_text('password = "supersecret123"\nprint(password)\n',encoding="utf-8")
        result=analyze(root);findings=[x for x in result["issues"] if x["file"]=="main.py"]
        assert [x["type"] for x in findings].count("SECRET")==1
        assert [x["type"] for x in findings].count("PASSWORD_LITERAL")==0


def test_scanner_finds_literal_div_zero():
    with TemporaryDirectory() as tmp:
        root=Path(tmp);(root/"main.py").write_text("value = 4 / 0\n",encoding="utf-8")
        result=analyze(root)
        assert any(x["type"]=="DIV_ZERO" and x["severity"]=="CRITICAL" for x in result["issues"])


def test_exception_engine_detects_bare_and_swallowed_handlers():
    with TemporaryDirectory() as tmp:
        root=Path(tmp);path=root/"bad.py"
        path.write_text('''def load():\n    try:\n        risky()\n    except:\n        pass\n''',encoding="utf-8")
        report=analyze_exceptions([path],{path:path.read_text(encoding="utf-8")},root)
        kinds={x["type"] for x in report["findings"]}
        assert "BARE_EXCEPT" in kinds and "SWALLOWED_EXCEPTION" in kinds
        assert report["score"] < 100 and report["recovery"]["swallowed"] == 1


def test_exception_engine_detects_finally_return():
    with TemporaryDirectory() as tmp:
        root=Path(tmp);path=root/"cleanup.py"
        path.write_text('''def work():\n    try:\n        risky()\n    finally:\n        return True\n''',encoding="utf-8")
        report=analyze_exceptions([path],{path:path.read_text(encoding="utf-8")},root)
        assert any(x["type"]=="FINALLY_RETURN" for x in report["findings"])


def test_exception_engine_does_not_abort_on_bad_python():
    with TemporaryDirectory() as tmp:
        root=Path(tmp);path=root/"broken.py";path.write_text("def broken(:\n",encoding="utf-8")
        report=analyze_exceptions([path],{path:path.read_text(encoding="utf-8")},root)
        assert report["findings"] == [] and report["analysis_errors"] == []


def test_graph_resolves_qualified_python_import_before_duplicate_stem():
    with TemporaryDirectory() as tmp:
        root=Path(tmp);(root/"pkg").mkdir();(root/"other").mkdir()
        (root/"pkg"/"__init__.py").write_text("",encoding="utf-8")
        (root/"pkg"/"alpha.py").write_text("x = 1\n",encoding="utf-8")
        (root/"other"/"alpha.py").write_text("x = 2\n",encoding="utf-8")
        (root/"main.py").write_text("from pkg import alpha\nprint(alpha.x)\n",encoding="utf-8")
        files=list(root.rglob("*.py"));contents={p:p.read_text(encoding="utf-8") for p in files};_,edges=build_graph(root,files,contents)
        targets={e["target"] for e in edges if e["source"]=="@file:main.py" and e["kind"]=="import" and e.get("token")=="pkg.alpha"}
        assert "@file:pkg/alpha.py" in targets and "@file:other/alpha.py" not in targets


def test_graph_does_not_guess_ambiguous_duplicate_stems():
    with TemporaryDirectory() as tmp:
        root=Path(tmp);(root/"a").mkdir();(root/"b").mkdir()
        (root/"a"/"util.py").write_text("x=1\n",encoding="utf-8");(root/"b"/"util.py").write_text("x=2\n",encoding="utf-8");(root/"main.py").write_text("import util\n",encoding="utf-8")
        files=list(root.rglob("*.py"));contents={p:p.read_text(encoding="utf-8") for p in files};_,edges=build_graph(root,files,contents)
        targets={e["target"] for e in edges if e["source"]=="@file:main.py" and e["kind"]=="import"}
        assert not ({"@file:a/util.py","@file:b/util.py"}&targets)


def test_scanner_does_not_flag_exception_alias_as_undefined():
    with TemporaryDirectory() as tmp:
        root=Path(tmp);(root/"main.py").write_text('''try:\n    risky()\nexcept Exception as exc:\n    print(exc)\n''',encoding="utf-8")
        result=analyze(root)
        assert not any(x["type"]=="UNDEFINED_NAME" and "exc" in x["title"] for x in result["issues"])


def test_scanner_ignores_secret_fixture_in_test_context():
    with TemporaryDirectory() as tmp:
        root=Path(tmp);tests=root/"tests";tests.mkdir();(tests/"test_auth.py").write_text('password = "supersecret123"\n',encoding="utf-8")
        result=analyze(root)
        assert not any(x["type"] in {"SECRET","PASSWORD_LITERAL"} for x in result["issues"])


def test_scanner_only_flags_high_confidence_dynamic_innerhtml():
    with TemporaryDirectory() as tmp:
        root=Path(tmp);(root/"safe.js").write_text('element.innerHTML = escapeHtml(value);\n',encoding="utf-8");(root/"unsafe.js").write_text('element.innerHTML = location.search;\n',encoding="utf-8")
        result=analyze(root)
        safe=[x for x in result["issues"] if x["file"]=="safe.js" and x["type"]=="DOM_XSS"];unsafe=[x for x in result["issues"] if x["file"]=="unsafe.js" and x["type"]=="DOM_XSS"]
        assert safe == [] and len(unsafe) == 1


def test_graph_prefers_exact_module_path():
    with TemporaryDirectory() as tmp:
        root=Path(tmp);(root/"pkg").mkdir();(root/"other").mkdir();(root/"pkg"/"alpha.py").write_text("x = 1\n",encoding="utf-8");(root/"other"/"alpha.py").write_text("x = 2\n",encoding="utf-8");(root/"main.py").write_text("from pkg import alpha\nprint(alpha.x)\n",encoding="utf-8")
        files=list(root.rglob("*.py"));contents={p:p.read_text(encoding="utf-8") for p in files};nodes,edges=build_graph(root,files,contents);main_id="@file:main.py"
        target_ids={e["target"] for e in edges if e["source"]==main_id and e["kind"]=="import"}
        assert "@file:pkg/alpha.py" in target_ids


def test_import_tokens_are_stable():
    tokens=import_tokens("import os\nfrom pkg import alpha\n",Path("main.py"))
    assert tokens==["os","pkg.alpha","pkg"]
