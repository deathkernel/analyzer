# PROJECT FORGE
## Professional Code Intelligence & Architecture Analysis Platform

### Feature & Technical Capability Report

**Repository:** github.com/deathkernel/analyzer  
**Positioning:** Local, read-only, polyglot software-intelligence cockpit

## 1. Executive Summary

Project Forge is a local software-intelligence platform for understanding a codebase as a connected system rather than a collection of isolated files. Its workflow is: scan the project, build a topology, detect quality and security signals, expose architectural relationships, and let an engineer investigate the result interactively.

The product combines a polyglot source scanner, live file watching, dependency graph, source exploration, security radar, project health metrics, evolution history, focused neural-style graph views, and an architecture-intelligence layer for impact, cycles, dead-code candidates, and Project X-Ray analysis.

The neural network in Forge is a visual architecture model: layers and nodes represent software topology and relationships. It is not a machine-learning model.

## 2. Feature Portfolio

| Feature | Explanation |
|---|---|
| Project Scanner | Discovers supported source files, skips common build/cache folders, reads source safely, and creates a consistent project inventory. |
| Polyglot Analysis | Supports a broad set of languages and configuration formats through one cockpit. |
| Code Metrics | Reports files, lines, functions, classes, imports, bytes, language distribution, and scan latency. |
| Code DNA | Produces complexity, coupling, duplication, security, maintainability, and architecture indicators. |
| Bug & Smell Detection | Flags syntax errors, undefined names, risky loops, bare exceptions, empty functions, literal index errors, secrets, command execution, SQL risks, DOM XSS signals, unsafe deserialization, and work-item markers. |
| Security Radar | Groups high-risk findings into a dedicated security view with a project security score. |
| Dependency Graph | Builds file/folder topology with import and inferred semantic relationships. |
| Neural Architecture Graph | Presents topology as a left-to-right, layered neural-style visual system with animated signals, node roles, focus, zoom, pan, and full-screen HUD presentation. |
| File Focus Mode | Selecting a file isolates its local neighborhood so relevant dependencies are easier to inspect. |
| Source Explorer | Provides file filtering, line counts, and in-app source inspection. |
| Global Search | Searches project content for symbols, strings, TODOs, imports, and other text patterns with direct source navigation. |
| Live Watcher | Detects file changes and triggers a fresh analysis cycle automatically. |
| Evolution History | Tracks health, issue counts, and critical/high findings across scans. |
| Impact Analysis | Estimates upstream and downstream dependencies and exposes a blast-radius view for a selected file. |
| Circular Dependency Detection | Identifies dependency cycles and reports participating nodes. |
| Dead Code Radar | Highlights potential orphan files and unreferenced Python functions/classes. |
| Project X-Ray | Summarizes architecture roles, entrypoints, data nodes, and entry-to-data flows. |
| Regression Tests + CI | Provides automated regression coverage and GitHub Actions checks for Python and JavaScript syntax. |

## 3. Neural Network Visualization

Forge includes a neural-style network view to make software architecture readable as a visual system.

Conceptually:

    INPUT
      |
      |\
      | \
      O--O
       \|
     HIDDEN 1
         |
       O-O-O
        \|/
      HIDDEN 2
         |
         O
      OUTPUT

The presentation can use layers such as INPUT, HIDDEN 1, HIDDEN 2, HIDDEN 3, HIDDEN 4, and OUTPUT. Nodes correspond to software modules or architectural roles, while connections represent dependencies and inferred relationships.

### How the neural view behaves

**Full Network** — The complete project topology remains available.

**Node Focus** — Selecting a file/node switches the viewport to a local neural neighborhood so the selected component and nearby relationships are easier to inspect.

**Signal Emphasis** — Real dependency links can be styled more strongly than inferred relationships, allowing evidence to remain visually distinguishable.

**Cinematic Interaction** — Zoom, pan, node dragging, animated flow, hover information, and full-screen HUD presentation make architecture investigation interactive rather than static.

**Engineering principle** — The neural visualization is a representation of software topology, not a learned ML model. The underlying facts come from deterministic source analysis and graph computation.

## 4. Technical Architecture

| Component | Responsibility |
|---|---|
| Scanner | Source discovery, text ingestion, language-aware checks, security and quality checks. |
| Graph Engine | Import resolution, semantic architecture edges, layered positioning, graph metrics, cycle analysis. |
| Intelligence Engine | Impact analysis, circular dependency detection, dead-code candidates, and X-Ray architecture reporting. |
| Local API / Watcher | Local HTTP delivery, project selection, state management, scan lifecycle, and live file monitoring. |
| Forge Cockpit | Source explorer, search, security radar, evolution view, neural graph, telemetry, and intelligence HUD. |

Overall flow:

    PROJECT FOLDER
          |
    SOURCE DISCOVERY
          |
    STATIC ANALYSIS
          |
    GRAPH CONSTRUCTION
          |
    INTELLIGENCE ENGINE
          |
       LOCAL API
          |
     FORGE COCKPIT

## 5. Core Investigation Workflows

### A. Find a project problem

Select a project -> run the scan -> review health and findings -> open the relevant file -> inspect source context.

### B. Understand a module

Open the Neural Graph -> select a file -> inspect its focused neighborhood -> use Impact Analysis to see upstream/downstream blast radius.

### C. Trace architecture

Open Project X-Ray -> inspect entrypoints, roles, and entry-to-data flows -> use the graph to follow specific paths.

### D. Investigate a security signal

Open Security Radar -> select a finding -> locate the source -> cross-reference graph relationships to understand exposure.

### E. Diagnose architectural drift

Compare evolution scans -> identify health changes -> inspect altered findings -> use graph and impact information to identify the modules driving the change.

## 6. Professional Value

**Faster codebase orientation** — Presents files, dependencies, architecture, and risk in one workspace.

**Safer change planning** — Impact analysis and focused graph views help reason about blast radius before editing central components.

**Higher-quality review** — Combines code findings with topology, allowing engineers to ask both “is this line risky?” and “what does this module affect?”.

**Architecture visibility** — X-Ray and semantic relationships reveal system structure beyond raw imports.

**Continuous feedback** — Live watching and scan history turn the analyzer into an always-on engineering feedback surface.

## 7. Recommended Product Direction

Forge should be positioned as a **local software-intelligence system**, not merely an “AI code scanner”.

Core principles:

1. **Evidence first** — scanner facts and graph relations remain the source of truth.
2. **Visual second** — the neural network is a human-friendly representation of software topology.
3. **Progressive depth** — summary -> node -> neighborhood -> impact -> architecture flow -> source evidence.
4. **Safe by default** — read-only local analysis reduces operational risk.
5. **Explainability** — important insights should be traceable to files, symbols, edges, and lines.

## 8. Operating Model

**Execution:** Run the local Python application, select a project directory, and open the locally served Forge cockpit.

**Analysis lifecycle:** Initial scan -> project state creation -> graph generation -> intelligence report -> UI refresh -> watcher-driven rescans.

**Data posture:** The product is intended as a local, read-only analyzer; source inspection and telemetry are surfaced from the selected project.

**Validation:** Regression tests and GitHub Actions checks are included to catch scanner and front-end regressions.

## 9. Current Capability vs. Next-Stage Roadmap

| Area | Current State | Recommended Upgrade |
|---|---|---|
| Parsing | Python AST + pattern analysis; broad language-aware heuristics | Multi-language AST parsers and symbol resolution |
| Graph | File-level dependencies + semantic edges + layered neural presentation | Function/class-level call graph and richer symbol references |
| Impact | File-level graph reachability | Function-level change simulation and path-specific impact |
| Security | Heuristic source signals | Taint/data-flow analysis from source to sink |
| Architecture | Role inference + X-Ray | Framework-aware architecture and boundary-violation detection |
| Performance | Hotspot heuristics | Complexity-aware profiling hints and repeated-I/O/N+1 detection |
| Testing | Regression suite + CI | Endpoint/function coverage mapping and critical-path test gaps |
| Reasoning | Structured intelligence HUD | Evidence-backed explain/why engine over analyzer facts |

## 10. Engineering Notes & Limitations

- Heuristic findings are signals requiring engineering review; static rules can produce false positives or miss context-dependent behavior.
- The neural visualization is a topology representation, not a learned neural model.
- File-level impact is useful for architectural triage, while function-level and symbol-level analysis would improve precision.
- Taint/data-flow analysis should be implemented before making strong claims about exploitability or end-to-end security paths.
- Large repositories will benefit from indexing, incremental analysis, caching, and graph virtualization as scale increases.

## 11. Conclusion

Project Forge has the foundation of a professional code-intelligence product: broad project discovery, structured findings, graph-based architecture visualization, live telemetry, source exploration, security signals, impact analysis, and an interactive neural-style interface.

The next maturity step is deeper semantic understanding — symbols, calls, data flow, framework semantics, and evidence-backed reasoning.

> **Product thesis:** Forge should make a codebase explainable as a living system — visually, structurally, and with traceable evidence.
