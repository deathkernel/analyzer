# PROJECT FORGE

Local, read-only, polyglot code-intelligence cockpit.

## Architecture

- `app.py` — local HTTP server, watcher, API surface, orchestration.
- `scanner.py` — language detection, source discovery, Python AST checks, security/quality heuristics, metrics and project DNA.
- `graph_engine.py` — dependency extraction, folder topology, layered graph layout and graph metrics.
- `index.html` — Forge command-center UI, source explorer, search, security radar, evolution telemetry and interactive neural graph.
- `style.css` — base cinematic visual system.

The old three-file constraint is intentionally removed. The project is now split by responsibility so new analysis engines can be added without turning one file into a monolith.

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
- Graph modes: all signals, dependencies, folder topology and hot-node focus.
- Node dragging, zoom, center, tracing, animated dependency flow, live packet HUD and graph telemetry.
- Responsive cockpit layout for smaller screens.

## Run

```bash
python app.py
```

Forge opens a local browser window and asks for the project folder to analyze. The target project is never modified by the analyzer.
