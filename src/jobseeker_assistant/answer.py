"""Answer building blocks: prompts, the Answer type, historical-page handling.

The flow itself (which step runs when) is the LangGraph graph in graph.py;
`answer_question` below runs it. Safety rules applied in code, not only in the prompt:
- Personal legal advice ("will I win my appeal?", "should I sue?") -> refusal before
  retrieval, whatever the sources say (legal_advice.py).
- No relevant passages            -> refusal, the LLM is not even called.
- Passages match too little of the question (coverage) -> refusal, LLM not called.
- Model says NOT_COVERED          -> refusal.
- Grounding self-check (grounding.py): every claim must cite a source it was given and be
  supported by it. If not -> one retry with stricter instructions -> then refusal.
- Every answer ends with the "rules change, check with Kela" note.

Historical pages: a retrieved historical page always brings its replacement page into the
sources. If the answer cites a historical page, the code itself appends the page's
"replaced by ... on 1 May 2026" note, citing both the old page and its replacement, so this
never depends on the model remembering. Refusal only if the replacement page isn't available.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .glossary import Term
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
DEFAULT_MIN_SCORE = 1.0  # passages below this BM25 score are dropped
# Refuse without calling the LLM unless some retrieved passage covers at least this share of
# the question (Index.coverage). Tuned on the golden set 2026-11-04: see PROGRESS.md.
DEFAULT_MIN_COVERAGE = 0.5
GATE_K = 4  # the coverage gate looks at the top 4 passages (what it was tuned on)
# Passages given to the model. Raised from 4 to 8 on 2026-11-04: in every recall miss the key
# fact was on the right page but ranked 5th-9th (see PROGRESS.md).
DEFAULT_K = 8

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
    also_on: tuple[str, ...] = ()  # other pages with the same text (deduplicated)


@dataclass
class Answer:
    text: str
    citations: list[Citation] = field(default_factory=list)
    refused: bool = False
    hits: list[Hit] = field(default_factory=list)
    added_notes: list[str] = field(default_factory=list)
    glossary_used: list[str] = field(default_factory=list)  # glossary terms that fired
    refusal_reason: str = ""  # why it refused, e.g. "legal_advice", "low_coverage"
    attempts: int = 0  # LLM calls: 0 (refused before the LLM), 1, or 2 (strict retry)
    path: list[str] = field(default_factory=list)  # graph nodes visited

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


def historical_notes(cited: list[int], hits: list[Hit]) -> tuple[list[str], list[int]] | None:
    """Notes to append for cited historical pages, and the source numbers they add.

    Returns None if a cited historical page's replacement isn't among the sources.
    """
    notes, extra = [], []
    seen_pages = set()
    for n in cited:
        tags = hits[n - 1].passage.tags
        url = hits[n - 1].passage.url
        if not tags.historical or url in seen_pages:
            continue
        seen_pages.add(url)
        labels = [n]
        if tags.replaced_by:
            m = next((i for i, h in enumerate(hits, 1) if h.passage.url == tags.replaced_by), None)
            if m is None:
                return None
            labels.append(m)
            if m not in cited:
                extra.append(m)
        note = tags.note or "This source describes rules that no longer apply."
        notes.append(f"Note: {note} " + "".join(f"[S{i}]" for i in labels))
    return notes, extra


def answer_question(
    question: str,
    index: Index,
    llm: LLM,
    k: int = DEFAULT_K,
    min_score: float = DEFAULT_MIN_SCORE,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
    glossary: list[Term] | None = None,
    gate_k: int = GATE_K,
) -> Answer:
    """Answer one question. Runs the LangGraph flow in graph.py."""
    from .graph import Settings, run_graph  # graph.py imports this module

    settings = Settings(k=k, min_score=min_score, min_coverage=min_coverage, gate_k=gate_k)
    answer, _ = run_graph(question, index, llm, glossary, settings)
    return answer
