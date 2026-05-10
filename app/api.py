"""
FastAPI application for OncoTargetMind Agent.
Provides POST /analyze endpoint.
"""

import os
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent.graph import run_analysis

app = FastAPI(
    title="OncoTargetMind Agent",
    description="Biomedical target discovery agent — minimal runnable version",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    text: str
    save_report: bool = False


class AnalyzeResponse(BaseModel):
    parsed: dict
    candidate_count: int
    scored_targets: list[dict]
    report: str
    error: str


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest):
    """
    Analyze clinical text and return ranked therapeutic targets.

    Input: free-text description including variants, up/down-regulated genes,
           and optionally cancer type.

    Returns scored and ranked candidate targets with a Markdown report.
    """
    result = run_analysis(request.text)

    if request.save_report and result.get("report"):
        os.makedirs("outputs", exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = f"outputs/report_{ts}.md"
        with open(path, "w", encoding="utf-8") as f:
            f.write(result["report"])

    return AnalyzeResponse(
        parsed=result.get("parsed", {}),
        candidate_count=len(result.get("candidate_targets", [])),
        scored_targets=result.get("scored_targets", []),
        report=result.get("report", ""),
        error=result.get("error", ""),
    )


@app.get("/health")
async def health():
    return {"status": "ok", "agent": "OncoTargetMind v0.1.0"}
