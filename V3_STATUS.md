# CodeFlow V3 — Code Intelligence

V3 adds the semantic intelligence layer on top of V2 parsing.

- Builds a typed node/edge result from discovered source files.
- Resolves unambiguous local import dependencies.
- Detects conservative same-file function/method calls.
- Collects diagnostics instead of failing the whole project scan.
- Adds regression tests for dependency, call, and summary behavior.

The visual graph remains a later version; V3 focuses on making the underlying relationships reliable first.
