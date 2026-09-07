from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Fix:
    rule: str
    title: str
    line: int
    severity: str
    confidence: str
    message: str
    replacement: str
    start: int
    end: int


def _fix_bare_except(text: str, path: Path) -> list[Fix]:
    if path.suffix.lower() != '.py':
        return []
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return []
    fixes = []
    lines = text.splitlines(keepends=True)
    offsets = []
    pos = 0
    for line in lines:
        offsets.append(pos)
        pos += len(line)
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            line = lines[node.lineno - 1]
            match = re.match(r'^(\s*)except\s*:', line)
            if not match:
                continue
            start = offsets[node.lineno - 1] + match.start() + len(match.group(1))
            end = start + len('except:')
            fixes.append(Fix(
                'BARE_EXCEPT', 'Replace bare except', node.lineno, 'MEDIUM', 'HIGH',
                'Catch Exception explicitly instead of every BaseException.',
                'except Exception:', start, end))
    return fixes


def _fix_none_comparisons(text: str, path: Path) -> list[Fix]:
    fixes = []
    if path.suffix.lower() not in {'.py'}:
        return fixes
    pattern = re.compile(r'(?P<expr>[A-Za-z_][\w.\[\]()]*)\s*(?P<op>==|!=)\s*None')
    lines = text.splitlines(keepends=True)
    offset = 0
    for lineno, line in enumerate(lines, 1):
        for m in pattern.finditer(line):
            op = 'is' if m.group('op') == '==' else 'is not'
            replacement = f"{m.group('expr')} {op} None"
            fixes.append(Fix('NONE_COMPARISON', 'Use identity comparison for None', lineno, 'LOW', 'HIGH',
                             'Python None checks should use is/is not.', replacement,
                             offset + m.start(), offset + m.end()))
        offset += len(line)
    return fixes


def analyze_fixes(root: Path, files: list[Path], contents: dict[Path, str], findings: list[dict]) -> dict:
    by_file = {Path(f): contents.get(Path(f), '') for f in files}
    fixes = []
    for f, text in by_file.items():
        fixes.extend(_fix_bare_except(text, f))
        fixes.extend(_fix_none_comparisons(text, f))
    known = {(x.get('file'), x.get('line'), x.get('type')) for x in findings}
    proposals = []
    for fix in fixes:
        rel = str(fix_file_rel(root, next((p for p in by_file if p.name and contents.get(p) == by_file.get(p)), Path('')))) if False else None
        proposals.append({
            'id': f'{fix.rule}:{fix.line}:{fix.start}',
            'rule': fix.rule, 'title': fix.title, 'line': fix.line,
            'severity': fix.severity, 'confidence': fix.confidence,
            'message': fix.message, 'replacement': fix.replacement,
        })
    return {'count': len(proposals), 'proposals': proposals, 'engine': 'LOCAL RULE ENGINE / NO AI API'}


def fix_file_rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root)).replace('\\', '/')
    except ValueError:
        return str(path).replace('\\', '/')


def build_file_fixes(root: Path, path: Path, text: str) -> list[dict]:
    raw = _fix_bare_except(text, path) + _fix_none_comparisons(text, path)
    return [
        {'id': f'{x.rule}:{x.line}:{x.start}', 'rule': x.rule, 'title': x.title,
         'line': x.line, 'severity': x.severity, 'confidence': x.confidence,
         'message': x.message, 'replacement': x.replacement,
         'start': x.start, 'end': x.end}
        for x in raw
    ]


def apply_fixes(text: str, fixes: list[dict]) -> tuple[str, list[dict]]:
    ordered = sorted(fixes, key=lambda x: int(x['start']), reverse=True)
    out = text
    applied = []
    last_start = len(text) + 1
    for f in ordered:
        start, end = int(f['start']), int(f['end'])
        if start < 0 or end < start or end > len(out) or start > last_start:
            continue
        out = out[:start] + f['replacement'] + out[end:]
        applied.append({'id': f['id'], 'rule': f['rule'], 'line': f['line'], 'title': f['title']})
        last_start = start
    return out, list(reversed(applied))
