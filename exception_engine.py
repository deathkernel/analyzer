from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path

SEVERITY_PENALTY = {"CRITICAL": 25, "HIGH": 12, "MEDIUM": 5, "LOW": 2}


def _issue(out, kind, file, line, title, message, severity="MEDIUM", column=None, **extra):
    item = {
        "type": kind,
        "category": "EXCEPTION_HANDLING",
        "file": file,
        "line": int(line or 0),
        "title": title,
        "message": message,
        "severity": severity,
    }
    if column:
        item["column"] = int(column)
    item.update(extra)
    out.append(item)


def _python_exception_checks(text: str, path: Path, root: Path, out: list[dict], metrics: Counter) -> None:
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return

    rel = str(path.relative_to(root)).replace("\\", "/")

    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue

        metrics["handlers"] += len(node.handlers)
        metrics["try_blocks"] += 1

        for handler in node.handlers:
            name = None
            if isinstance(handler.type, ast.Name):
                name = handler.type.id
            elif isinstance(handler.type, ast.Attribute):
                name = handler.type.attr

            if handler.type is None:
                _issue(out, "BARE_EXCEPT", rel, handler.lineno, "Bare except", "Catches every exception type. Catch only the failures the code can actually recover from.", "HIGH", getattr(handler, "col_offset", 0) + 1, rule="bare-except")
                metrics["bare"] += 1
            elif name in {"Exception", "BaseException"}:
                _issue(out, "BROAD_EXCEPTION", rel, handler.lineno, "Broad exception handler", f"Catches {name}; this can hide programming errors and unrelated failures.", "MEDIUM" if name == "Exception" else "HIGH", getattr(handler, "col_offset", 0) + 1, rule="broad-except", exception=name)
                metrics["broad"] += 1

            body = [x for x in handler.body if not (isinstance(x, ast.Expr) and isinstance(x.value, ast.Constant) and isinstance(x.value.value, str))]
            if body and all(isinstance(x, ast.Pass) for x in body):
                _issue(out, "SWALLOWED_EXCEPTION", rel, handler.lineno, "Exception is swallowed", "The handler ignores the failure completely. This makes production failures difficult to observe and debug.", "HIGH", getattr(handler, "col_offset", 0) + 1, rule="swallowed-exception")
                metrics["swallowed"] += 1

            has_raise = any(isinstance(x, ast.Raise) for x in ast.walk(handler))
            has_logging = any(
                isinstance(x, ast.Call)
                and isinstance(x.func, ast.Attribute)
                and x.func.attr in {"debug", "info", "warning", "error", "exception", "critical", "log"}
                for x in ast.walk(handler)
            )
            if has_raise:
                metrics["reraised"] += 1
            if has_logging:
                metrics["logged"] += 1

            if name in {"Exception", "BaseException"} and not has_raise and not has_logging and body:
                _issue(out, "UNOBSERVED_BROAD_HANDLER", rel, handler.lineno, "Broad handler without recovery signal", "A broad exception is caught without a visible log or re-raise. Review whether the failure is being silently hidden.", "HIGH", getattr(handler, "col_offset", 0) + 1, rule="unobserved-broad-handler")
                metrics["unobserved_broad"] += 1

        if node.finalbody:
            for stmt in node.finalbody:
                if isinstance(stmt, ast.Return):
                    _issue(out, "FINALLY_RETURN", rel, stmt.lineno, "Return inside finally", "Returning from finally can suppress an active exception. Prefer cleanup-only code in finally blocks.", "HIGH", getattr(stmt, "col_offset", 0) + 1, rule="finally-return")
                    metrics["finally_return"] += 1
                elif isinstance(stmt, ast.Raise):
                    _issue(out, "FINALLY_RAISE", rel, stmt.lineno, "Raise inside finally", "Raising from finally can replace the original failure. Preserve the original exception when cleanup itself fails.", "MEDIUM", getattr(stmt, "col_offset", 0) + 1, rule="finally-raise")
                    metrics["finally_raise"] += 1


def _generic_exception_checks(text: str, path: Path, root: Path, out: list[dict], metrics: Counter) -> None:
    ext = path.suffix.lower()
    rel = str(path.relative_to(root)).replace("\\", "/")
    lines = text.splitlines()

    patterns = []
    if ext in {".js", ".jsx", ".ts", ".tsx"}:
        patterns = [
            (re.compile(r"catch\s*\([^)]*\)\s*\{\s*\}", re.I), "EMPTY_CATCH", "Empty catch block", "An empty catch block discards the failure context.", "HIGH"),
            (re.compile(r"catch\s*\([^)]*\)\s*\{\s*(?:/\*.*?\*/|//[^\n]*)?\s*\}", re.I), "EMPTY_CATCH", "Empty catch block", "The caught error is not visibly handled.", "HIGH"),
        ]
    elif ext in {".java", ".kt", ".cs"}:
        patterns = [
            (re.compile(r"catch\s*\([^)]*(?:Exception|Throwable|SystemException)[^)]*\)\s*\{", re.I), "BROAD_EXCEPTION", "Broad exception handler", "Review whether the handler catches failures it cannot safely recover from.", "MEDIUM"),
        ]

    for pattern, kind, title, message, severity in patterns:
        for no, line in enumerate(lines, 1):
            if pattern.search(line):
                _issue(out, kind, rel, no, title, message, severity, rule="generic-exception-pattern")
                metrics["generic_findings"] += 1

    if ext in {".js", ".jsx", ".ts", ".tsx"}:
        for no, line in enumerate(lines, 1):
            if re.search(r"catch\s*\([^)]*\)\s*\{", line, re.I):
                metrics["handlers"] += 1


def analyze_exceptions(files, contents, root: Path) -> dict:
    """Analyze exception/error handling without executing target code.

    The function is intentionally defensive: one malformed/unsupported file
    must never abort the repository-wide exception analysis.
    """
    root = Path(root).resolve()
    findings = []
    metrics = Counter()
    file_errors = []

    for path in files:
        try:
            text = contents.get(path, "")
            if path.suffix.lower() == ".py":
                _python_exception_checks(text, path, root, findings, metrics)
            else:
                _generic_exception_checks(text, path, root, findings, metrics)
        except (OSError, UnicodeError, ValueError, RecursionError) as exc:
            file_errors.append({
                "file": str(path.relative_to(root)).replace("\\", "/"),
                "error": f"{type(exc).__name__}: {exc}",
            })
            metrics["analysis_errors"] += 1

    unique = []
    seen = set()
    for finding in findings:
        key = (finding["type"], finding["file"], finding["line"], finding["title"])
        if key not in seen:
            seen.add(key)
            unique.append(finding)

    severity = Counter(x["severity"] for x in unique)
    handler_count = metrics["handlers"]
    risky = severity["CRITICAL"] + severity["HIGH"] + severity["MEDIUM"] + severity["LOW"]
    score = max(0, 100 - sum(severity[k] * SEVERITY_PENALTY[k] for k in SEVERITY_PENALTY))
    if handler_count and not unique:
        score = min(100, score + 2)

    return {
        "findings": unique,
        "metrics": dict(metrics),
        "severity": dict(severity),
        "score": score,
        "handlers": handler_count,
        "risky_findings": risky,
        "recovery": {
            "logged": metrics["logged"],
            "reraised": metrics["reraised"],
            "swallowed": metrics["swallowed"],
        },
        "analysis_errors": file_errors,
    }
