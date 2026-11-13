"""HTTP API for the disease-to-target agent.

Run locally:   uvicorn api:app --reload
Then open:     http://127.0.0.1:8000        (demo page)
               http://127.0.0.1:8000/docs   (interactive API docs)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from d2t import __version__
from d2t.agent import RESEARCH_LABEL

log = logging.getLogger("d2t.api")
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="Disease-to-Target Agent",
    version=__version__,
    description=(
        "Give a disease; an LLM agent searches PubMed, reads abstracts and verifies up to three "
        "candidate protein targets in UniProtKB. Research use only - not medical advice."
    ),
)


class AnalyzeRequest(BaseModel):
    disease: str = Field(..., min_length=2, max_length=100, examples=["Parkinson's disease"])

    @field_validator("disease")
    @classmethod
    def strip_and_check(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 2:
            raise ValueError("disease must contain at least 2 non-space characters")
        return value


class AnalyzeResponse(BaseModel):
    disease: str
    report: str = Field(description="Markdown report with candidates, links and evidence notes")
    tools_used: list[str] = Field(description="Tool calls the agent made, in order")
    label: str = RESEARCH_LABEL


Runner = Callable[[str], dict[str, Any]]


def get_runner() -> Runner:
    """Dependency, so tests can swap the real (slow, paid) agent for a fake one."""
    from d2t.agent import run_agent

    return run_agent


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(body: AnalyzeRequest, runner: Runner = Depends(get_runner)) -> AnalyzeResponse:
    # Plain `def` (not async): FastAPI runs it in a worker thread, so a slow agent run
    # does not block other requests.
    try:
        result = runner(body.disease)
    except RuntimeError as exc:  # e.g. missing GROQ_API_KEY
        log.error("Agent not configured: %s", exc)
        raise HTTPException(status_code=503, detail="The agent is not configured on this server.")
    except Exception as exc:  # upstream API/model failure, step limit reached, etc.
        log.exception("Agent run failed for %r", body.disease)
        raise HTTPException(
            status_code=502, detail=f"The agent could not finish: {type(exc).__name__}"
        )
    return AnalyzeResponse(disease=body.disease, **result)
