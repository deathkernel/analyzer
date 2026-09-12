from __future__ import annotations

from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field


class NodeType(StrEnum):
    FILE = "file"
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    VARIABLE = "variable"
    IMPORT = "import"


class EdgeType(StrEnum):
    CONTAINS = "contains"
    IMPORTS = "imports"
    CALLS = "calls"
    DEFINES = "defines"
    REFERENCES = "references"


class CodeNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    type: NodeType
    symbol: str
    file: str
    line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    language: str
    metadata: dict[str, str] = Field(default_factory=dict)


class CodeEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str
    target: str
    type: EdgeType
    label: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class AnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    root: str
    nodes: list[CodeNode] = Field(default_factory=list)
    edges: list[CodeEdge] = Field(default_factory=list)
    files_scanned: int = 0
    errors: list[str] = Field(default_factory=list)
