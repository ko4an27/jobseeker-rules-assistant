"""HTTP API: POST /ask, GET /health.

    make api            # uvicorn on http://127.0.0.1:8000  (docs at /docs)

Privacy (CLAUDE.md rule 5): the question text is never logged or stored. Logs and traces
get only metadata: question length, path through the graph, refusal reason, latency.

Abuse protection (security.py): /ask is rate limited per client (RATE_LIMIT_PER_MINUTE,
default 10) and, if API_KEY is set, needs the header `X-API-Key`. /health stays open.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from . import snapshots
from .answer import DISCLAIMER
from .glossary import Term, load_glossary
from .graph import run_graph
from .llm import LLM, get_llm
from .retrieve import Index
from .security import RateLimiter, api_key_from_env, key_ok, rate_limit_from_env
from .source_tags import load_tags
from .tracing import Tracer, get_tracer

MAX_QUESTION_CHARS = 500
log = logging.getLogger("jobseeker_assistant.api")


class AskRequest(BaseModel):
    question: str = Field(
        ..., max_length=MAX_QUESTION_CHARS, examples=["How long can a work try-out last?"]
    )

    @field_validator("question")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("question must not be empty")
        return value


class CitationOut(BaseModel):
    label: str
    url: str
    section: str
    fetched_at: str
    historical: bool


class AskResponse(BaseModel):
    answer: str
    refused: bool
    refusal_reason: str | None
    citations: list[CitationOut]
    path: list[str]
    attempts: int
    disclaimer: str
    request_id: str


@dataclass
class Resources:
    index: Index
    llm: LLM
    glossary: list[Term]
    tracer: Tracer
    snapshot_count: int


def load_resources() -> Resources:
    snaps = snapshots.load_all()
    return Resources(
        index=Index.from_snapshots(snaps, load_tags()),
        llm=get_llm(),
        glossary=load_glossary(),
        tracer=get_tracer(),
        snapshot_count=len(snaps),
    )


def create_app(
    resources: Resources | None = None,
    rate_limiter: RateLimiter | None = None,
    api_key: str | None = None,
) -> FastAPI:
    """`rate_limiter` / `api_key` default to RATE_LIMIT_PER_MINUTE / API_KEY from env."""
    limiter = rate_limiter or RateLimiter(rate_limit_from_env())
    expected_key = api_key_from_env() if api_key is None else api_key
    app = FastAPI(
        title="Jobseeker Rules Assistant",
        description="Answers from official Finnish sources only, with citations. "
        "Not legal or official advice.",
        version="0.1.0",
    )
    state: dict[str, Resources] = {}

    def res() -> Resources:
        if "r" not in state:  # load lazily, so importing the app has no side effects
            try:
                state["r"] = resources or load_resources()
            except (RuntimeError, ValueError) as exc:  # e.g. no API key configured
                raise HTTPException(status_code=503, detail=f"not configured: {exc}") from exc
        return state["r"]

    @app.get("/health")
    def health() -> dict:
        r = res()
        return {
            "status": "ok" if r.snapshot_count else "no_sources",
            "snapshots": r.snapshot_count,
            "llm": type(r.llm).__name__,
            "tracing": r.tracer.enabled,
            "api_key_required": bool(expected_key),
            "rate_limit_per_minute": limiter.limit,
        }

    @app.post("/ask", response_model=AskResponse)
    def ask(
        req: AskRequest,
        request: Request,
        x_api_key: str | None = Header(default=None),
    ) -> AskResponse:
        if not key_ok(expected_key, x_api_key):
            raise HTTPException(status_code=401, detail="missing or wrong X-API-Key header")
        client = request.client.host if request.client else "unknown"
        wait = limiter.check(client)
        if wait:
            raise HTTPException(
                status_code=429,
                detail="too many requests, try again shortly",
                headers={"Retry-After": str(max(1, round(wait)))},
            )
        r = res()
        request_id = uuid.uuid4().hex[:12]
        started = time.perf_counter()
        answer, path = run_graph(req.question, r.index, r.llm, r.glossary)
        latency_ms = round((time.perf_counter() - started) * 1000)
        meta = {
            "request_id": request_id,
            "question_chars": len(req.question),
            "path": path,
            "refused": answer.refused,
            "refusal_reason": answer.refusal_reason or None,
            "attempts": answer.attempts,
            "cited_urls": sorted({c.url for c in answer.citations}),
            "latency_ms": latency_ms,
        }
        log.info("ask %s", meta)  # metadata only, never the question text
        r.tracer.record_answer(question=req.question, answer=answer.text, metadata=meta)
        return AskResponse(
            answer=answer.text,
            refused=answer.refused,
            refusal_reason=answer.refusal_reason or None,
            citations=[
                CitationOut(
                    label=c.label,
                    url=c.url,
                    section=c.section,
                    fetched_at=c.fetched_at,
                    historical=c.historical,
                )
                for c in answer.citations
            ],
            path=path,
            attempts=answer.attempts,
            disclaimer=DISCLAIMER,
            request_id=request_id,
        )

    return app


app = create_app()
