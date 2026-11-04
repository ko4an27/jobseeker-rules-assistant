"""Simple RAG: question -> top passages -> LLM answer with citations -> safety checks.

Safety rules applied in code, not only in the prompt:
- No relevant passages            -> refusal, the LLM is not even called.
- Model says NOT_COVERED          -> refusal.
- Answer has no [S#] citation     -> refusal (an uncited claim can't be checked).
- Answer cites a source we did not give it -> refusal (invented citation).
- Answer cites a HISTORICAL page but not the page that replaced it -> refusal.
- Every answer ends with the "rules change, check with Kela" note.

Historical pages that are retrieved always bring their replacement page into the sources,
so the model can say what replaced the old benefit and cite both.
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
- If sources disagree or may be outdated, say so.
- Sources marked HISTORICAL describe rules that no longer apply. If you use one, say clearly \
that it was replaced (the label says by what and when) and cite both the historical source \
and the current source. Base the current rules on the current source.
- Sources marked FOR EMPLOYERS are written for employers. Answer from the jobseeker's point \
of view: explain what it means for the jobseeker; do not give employer instructions as if \
the user were the employer."""

_CITATION = re.compile(r"\[S(\d+)\]")


@dataclass(frozen=True)
class Citation:
    label: str  # "S1"
    url: str
    section: str
    fetched_at: str
    historical: bool = False


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
                old = " [historical]" if c.historical else ""
                out.append(
                    f"[{c.label}] {c.url} — section: {c.section}{old} (fetched {c.fetched_at})"
                )
        out.append(f"\n{DISCLAIMER}")
        return "\n".join(out)


def source_label(hit: Hit) -> str:
    """Warnings shown to the model next to a source, from the page's tags."""
    tags = hit.passage.tags
    labels = []
    if tags.historical:
        labels.append(f"[HISTORICAL: {tags.note or 'these rules no longer apply'}]")
    if tags.audience == "employer":
        labels.append("[FOR EMPLOYERS]")
    return (" " + " ".join(labels)) if labels else ""


def build_user_prompt(question: str, hits: list[Hit]) -> str:
    blocks = []
    for i, hit in enumerate(hits, start=1):
        p = hit.passage
        blocks.append(f"[S{i}] {p.title} — {p.section} ({p.url}){source_label(hit)}\n{p.text}")
    return "Sources:\n\n" + "\n\n".join(blocks) + f"\n\nQuestion: {question}"


def add_replacements(question: str, hits: list[Hit], index: Index) -> list[Hit]:
    """For every historical page among the hits, make sure its replacement page is there too."""
    hits = list(hits)
    for hit in list(hits):
        new_url = hit.passage.tags.replaced_by
        if new_url and all(h.passage.url != new_url for h in hits):
            replacement = index.best_from_url(new_url, question)
            if replacement:
                hits.append(replacement)
    return hits


def missing_replacement(cited: list[Hit]) -> bool:
    """True if a cited historical page's replacement is not cited as well."""
    cited_urls = {h.passage.url for h in cited}
    return any(
        h.passage.tags.replaced_by and h.passage.tags.replaced_by not in cited_urls for h in cited
    )


def _refuse(hits: list[Hit]) -> Answer:
    return Answer(text=REFUSAL, refused=True, hits=hits)


def answer_question(
    question: str, index: Index, llm: LLM, k: int = 4, min_score: float = 1.0
) -> Answer:
    hits = [h for h in index.search(question, k=k) if h.score >= min_score]
    if not hits:
        return _refuse(hits)
    hits = add_replacements(question, hits, index)

    raw = llm.complete(SYSTEM_PROMPT, build_user_prompt(question, hits)).strip()
    if not raw or NOT_COVERED in raw:
        return _refuse(hits)

    cited = sorted({int(n) for n in _CITATION.findall(raw)})
    if not cited or any(n < 1 or n > len(hits) for n in cited):
        return _refuse(hits)

    if missing_replacement([hits[n - 1] for n in cited]):
        return _refuse(hits)

    citations = []
    for n in cited:
        p = hits[n - 1].passage
        citations.append(Citation(f"S{n}", p.url, p.section, p.fetched_at, p.tags.historical))
    return Answer(text=raw, citations=citations, hits=hits)
