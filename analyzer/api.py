from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .engine import analyze_project

app = FastAPI(title="CodeFlow Analyzer", version="0.1.0")


class AnalyzeRequest(BaseModel):
    root: str = Field(min_length=1)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "codeflow-analyzer"}


@app.post("/api/analyze")
def analyze(request: AnalyzeRequest):
    result = analyze_project(request.root)
    if result.errors:
        raise HTTPException(status_code=400, detail=result.errors)
    return result
