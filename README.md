# CodeFlow

CodeFlow is a local-first code intelligence platform that explains how software flows.

## 8-version roadmap

1. V1 — Foundation
2. V2 — Parser Engine
3. V3 — Code Intelligence
4. V4 — Flow Graph
5. V5 — Visual Engine
6. V6 — Trace & Impact
7. V7 — Advanced Intelligence
8. V8 — Production

## V1 — Foundation

Python/FastAPI backend, strict TypeScript/React frontend, typed graph-domain models, safe project discovery and a clean API boundary.

## V2 — Parser Engine

V2 adds language-aware extraction for **Python, JavaScript, JSX, TypeScript and TSX**. Python uses the standard-library AST for syntax-aware parsing; JS/TS uses conservative declaration/import extraction while keeping the output in the same typed semantic model.

### Backend

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
uvicorn analyzer.api:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Run parser tests with:

```bash
pytest
```

The analyzer is read-only: it discovers and analyzes source files without modifying the target project.
