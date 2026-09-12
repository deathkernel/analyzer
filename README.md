# CodeFlow

Local, read-only, polyglot code-flow intelligence cockpit.

## Core idea

CodeFlow analyzes a project and turns its discovered architecture, dependencies, semantic relationships, tracing paths and code signals into an interactive n8n-style visual flow map. The graph is generated from the codebase; it is not a manually authored workflow.

## Architecture

- `app.py` — local HTTP server, watcher, API surface and CodeFlow orchestration.
- `scanner.py` — language detection, source discovery, Python AST checks, security/quality heuristics, metrics and project DNA.
- `graph_engine.py` — dependency extraction, semantic framework relationships, folder topology, layered graph layout and graph metrics.
- `index.html` — CodeFlow command-center UI, source explorer, search, security radar, evolution telemetry and interactive neural flow graph.
- `style.css` — base visual system.

## Current capabilities

- Continuous read-only project scanning.
- Multi-language source discovery.
- Python AST analysis plus cross-language security/quality heuristics.
- Undefined names, syntax errors, division-by-zero, infinite-loop risk, bare exceptions, empty functions and literal index errors.
- Secret/password detection, dynamic execution, command execution, SQL-injection patterns, DOM XSS, unsafe pickle deserialization and work-item markers.
- Project DNA: complexity, coupling, duplication proxy, maintainability and security signals.
- Live project health and scan history.
- Source explorer with line-numbered code viewer.
- Global code search.
- Security radar.
- Dependency + folder architecture graph.
- Semantic neural flow graph that infers runtime relationships such as entrypoint → routes, routes → database, route → template, template → asset and template composition.
- Node dragging, zoom, center, tracing, animated dependency flow, live packet HUD and graph telemetry.
- Responsive cockpit layout for smaller screens.
- Stable multi-file import resolution with ambiguity-aware stem matching and Python from-import support.
- Graph interaction fixes: one zoom controller, safe render scheduling, bounded node dragging and correct hot-node highlighting.
- More meaningful duplication scoring based on repeated normalized lines rather than line length alone.
- Regression tests for secret finding de-duplication, literal division-by-zero detection, import graph resolution and token extraction.

## Run

```bash
python app.py
```

CodeFlow opens a local browser window and asks for the project folder to analyze. The target project is never modified by the analyzer.
