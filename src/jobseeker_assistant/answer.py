"""Simple RAG: question -> top passages -> LLM answer with citations -> safety checks.

Safety rules applied in code, not only in the prompt:
- No relevant passages            -> refusal, the LLM is not even called.
- Model says NOT_COVERED          -> refusal.
- Answer has no [S#] citation     -> refusal (an uncited claim can't be checked).
- Answer cites a source we did not give it -> refusal (invented citation).
- Every answer ends with the "rules change, check with Kela" note.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .llm import LLM
from .retrieve import Hit, Index

REFUSAL = (
    "I can't confirm this from official sources. Please ask Kela (kela.fi) about benefits, "
    "or your local employment services (tyomarkkinatori.fi) about jobseeking services."
)
DISCLAIMER = (
    "Note: this is not legal or official advice. Rules change; check with Kela or your "
    "employment office before you act."
)
NOT_COVERED = "NOT_COVERED"

SYSTEM_PROMPT = f"""You answer jobseekers' questions about Finnish unemployment rules and \
employment services.

Rules:
- Use ONLY the numbered sources in the user message. Do not use outside knowledge.
- After every sentence that states a fact, cite its source like [S1] or [S1][S3].
- If the sources do not answer the question, reply with exactly: {NOT_COVERED}
- Plain, short language (max ~120 words). No legal promises. Do not ask for personal data.
- If sources disagree or may be outdated, say so."""

_CITATION = re.compile(r"\[S(\d+)\]")


@dataclass(frozen=True)
class Citation:
    label: str  # "S1"
    url: str
    section: str
    fetched_at: str


@dataclass
class Answer:
    text: str
    citations: list[Citation] = field(default_factory=list)
    refused: bool = False
    hits: list[Hit] = field(default_factory=list)

    def render(self) -> str:
        out = [self.text]
        if self.citations:
            out.append("\nSources:")
            for c in self.citations:
                out.append(f"[{c.label}] {c.url} — section: {c.section} (fetched {c.fetched_at})")
        out.append(f"\n{DISCLAIMER}")
        return "\n".join(out)


def build_user_prompt(question: str, hits: list[Hit]) -> str:
    blocks = []
    for i, hit in enumerate(hits, start=1):
        p = hit.passage
        blocks.append(f"[S{i}] {p.title} — {p.section} ({p.url})\n{p.text}")
    return "Sources:\n\n" + "\n\n".join(blocks) + f"\n\nQuestion: {question}"


def _refuse(hits: list[Hit]) -> Answer:
    return Answer(text=REFUSAL, refused=True, hits=hits)


def answer_question(
    question: str, index: Index, llm: LLM, k: int = 4, min_score: float = 1.0
) -> Answer:
    hits = [h for h in index.search(question, k=k) if h.score >= min_score]
    if not hits:
        return _refuse(hits)

    raw = llm.complete(SYSTEM_PROMPT, build_user_prompt(question, hits)).strip()
    if not raw or NOT_COVERED in raw:
        return _refuse(hits)

    cited = sorted({int(n) for n in _CITATION.findall(raw)})
    if not cited or any(n < 1 or n > len(hits) for n in cited):
        return _refuse(hits)

    citations = []
    for n in cited:
        p = hits[n - 1].passage
        citations.append(Citation(f"S{n}", p.url, p.section, p.fetched_at))
    return Answer(text=raw, citations=citations, hits=hits)
