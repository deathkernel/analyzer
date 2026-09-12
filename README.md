# CodeFlow

CodeFlow is a local-first code intelligence platform that explains how software flows.

## Architecture

- **Python / FastAPI** — analysis engine and API boundary
- **TypeScript / React** — typed developer interface
- **Semantic graph** — functions, classes, modules and relationships
- **Versioned delivery** — V1 through V8, with each milestone kept independently reviewable

## V1 — Foundation

V1 establishes the clean project boundary, typed domain models, safe source discovery, FastAPI health/analyze endpoints, and a strict TypeScript React shell.

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

## V2 — Parser Engine

V2 adds language-aware parsing for Python and JavaScript/TypeScript using Python's standard AST for Python and a conservative lexical parser for JS/TS. The parser emits the same typed semantic model, so later graph and UI versions do not depend on parser-specific structures.
