"""The answer flow as a LangGraph state graph.

    legal_check ──refuse──▶ refuse
        │
    retrieve ─────refuse──▶ refuse        (no passage above the score floor)
        │
    coverage_gate ─refuse─▶ refuse        (passages match too little of the question)
        │
    generate ─────refuse──▶ refuse        (model says NOT_COVERED)
        │
    check_grounding ──fail, 1st time──▶ generate (strict retry) ──▶ check_grounding
        │            └─fail again────▶ refuse
        ▼ ok
    finalize ─────refuse──▶ refuse        (historical page's replacement unavailable)
        │
       END

    If the question names an abolished benefit (sources/abolished.toml), every "refuse"
    except legal advice goes to note_only instead: the answer is just the checked, cited
    "abolished on 1 May 2026" note. finalize always appends that note too.

Each node does one job and records its name in `path`, so a test (or a trace) can see
exactly which way a question went. The safety gates run before any LLM call.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from . import legal_advice
from .abolished import Abolished, add_notes, load_abolished, mentioned
from .answer import (
    _CITATION,
    DEFAULT_K,
    DEFAULT_MIN_COVERAGE,
    DEFAULT_MIN_SCORE,
    GATE_K,
    NOT_COVERED,
    REFUSAL,
    SYSTEM_PROMPT,
    Answer,
    Citation,
    add_replacements,
    build_user_prompt,
    historical_notes,
)
from .glossary import Term, expand
from .grounding import GroundingResult, check_answer
from .llm import LLM
from .retrieve import Hit, Index

MAX_ATTEMPTS = 2  # first answer + one strict retry

STRICT_SYSTEM_PROMPT = (
    SYSTEM_PROMPT
    + """

STRICT MODE — your previous answer had claims the sources do not support.
- Write fewer, shorter sentences. Each sentence must restate what ONE cited source says,
  using the source's own words and numbers.
- Every sentence must end with its citation, e.g. [S2]. Only cite sources listed above.
- Leave out anything you cannot cite. If nothing can be cited, reply exactly: """
    + NOT_COVERED
)


@dataclass(frozen=True)
class Settings:
    k: int = DEFAULT_K
    min_score: float = DEFAULT_MIN_SCORE
    min_coverage: float = DEFAULT_MIN_COVERAGE
    gate_k: int = GATE_K


class State(TypedDict, total=False):
    question: str
    retrieval_query: str
    coverage_query: str
    glossary_used: list[str]
    hits: list[Hit]
    draft: str
    attempts: int
    grounding: GroundingResult
    refusal_reason: str
    refusal_text: str
    answer: Answer
    mentions: list[Abolished]  # abolished benefits/offices named in the question
    path: Annotated[list[str], operator.add]  # node names, appended by every node


def build_graph(
    index: Index,
    llm: LLM,
    glossary: list[Term] | None = None,
    settings=None,
    abolished: list[Abolished] | None = None,
):
    settings = settings or Settings()
    glossary = glossary or []
    abolished = load_abolished() if abolished is None else abolished

    def legal_check(state: State) -> State:
        rule = legal_advice.detect(state["question"])
        if rule:
            return {
                "path": ["legal_check"],
                "refusal_reason": f"legal_advice:{rule}",
                "refusal_text": legal_advice.LEGAL_ADVICE_REFUSAL,
            }
        return {"path": ["legal_check"], "mentions": mentioned(state["question"], abolished)}

    def retrieve(state: State) -> State:
        exp = expand(state["question"], glossary)
        hits = [
            h
            for h in index.search(exp.retrieval_query, k=settings.k)
            if h.score >= settings.min_score
        ]
        update: State = {
            "path": ["retrieve"],
            "retrieval_query": exp.retrieval_query,
            "coverage_query": exp.coverage_query,
            "glossary_used": [t.match[0] for t in exp.used],
            "hits": hits,
        }
        if not hits:
            update["refusal_reason"] = "no_passages"
        return update

    def coverage_gate(state: State) -> State:
        gate_hits = state["hits"][: settings.gate_k]
        best = max(index.coverage(state["coverage_query"], h.passage) for h in gate_hits)
        if best < settings.min_coverage:
            return {"path": ["coverage_gate"], "refusal_reason": "low_coverage"}
        # Covered: bring in the replacement page of any historical page among the sources.
        hits = add_replacements(state["retrieval_query"], state["hits"], index)
        return {"path": ["coverage_gate"], "hits": hits}

    def generate(state: State) -> State:
        attempts = state.get("attempts", 0)
        user = build_user_prompt(state["question"], state["hits"])
        if attempts == 0:
            system = SYSTEM_PROMPT
        else:
            system = STRICT_SYSTEM_PROMPT
            problems = "\n".join(
                f"- {c.claim} ({c.reason})" for c in state["grounding"].unsupported
            )
            user += f"\n\nThese sentences of your previous answer were not supported:\n{problems}"
        draft = llm.complete(system, user).strip()
        update: State = {
            "path": ["generate" if attempts == 0 else "generate_strict"],
            "draft": draft,
            "attempts": attempts + 1,
        }
        if not draft or NOT_COVERED in draft:
            update["refusal_reason"] = "not_covered"
        return update

    def check_grounding(state: State) -> State:
        result = check_answer(state["draft"], state["hits"])
        update: State = {"path": ["check_grounding"], "grounding": result}
        if not result.ok and state["attempts"] >= MAX_ATTEMPTS:
            update["refusal_reason"] = "not_grounded"
        return update

    def finalize(state: State) -> State:
        hits, text = state["hits"], state["draft"]
        cited = sorted({int(c) for c in _CITATION.findall(text)})
        # Abolished benefit named in the question: always add its note (checked, cited).
        hits, notes, extra, covered = add_notes(state.get("mentions", []), hits, index, cited)
        result = historical_notes(cited, hits, covered)
        if result is None:
            return {"path": ["finalize"], "refusal_reason": "replacement_unavailable"}
        notes = result[0] + notes
        extra = result[1] + extra
        if notes:
            text = text + "\n\n" + "\n".join(notes)
            cited = sorted(set(cited) | set(extra))
        citations = [_citation(n, hits) for n in cited]
        answer = Answer(
            text=text,
            citations=citations,
            hits=hits,
            added_notes=notes,
            glossary_used=state.get("glossary_used", []),
            attempts=state["attempts"],
        )
        return {"path": ["finalize"], "answer": answer}

    def refuse(state: State) -> State:
        answer = Answer(
            text=state.get("refusal_text") or REFUSAL,
            refused=True,
            hits=state.get("hits", []),
            glossary_used=state.get("glossary_used", []),
            refusal_reason=state["refusal_reason"],
            attempts=state.get("attempts", 0),
        )
        return {"path": ["refuse"], "answer": answer}

    def note_only(state: State) -> State:
        """The normal answer failed, but the question names an abolished benefit: answer with
        just its (checked, cited) note instead of a refusal."""
        hits, notes, extra, _ = add_notes(state["mentions"], state.get("hits", []), index, [])
        if not notes:
            return {"path": ["note_only"]}  # nothing backed by a source: refuse after all
        citations = [_citation(n, hits) for n in sorted(set(extra))]
        answer = Answer(
            text="\n".join(notes),
            citations=citations,
            hits=hits,
            added_notes=notes,
            glossary_used=state.get("glossary_used", []),
            attempts=state.get("attempts", 0),
        )
        return {"path": ["note_only"], "answer": answer}

    def failed(state: State) -> str:
        """Where a failed step goes: the abolished-benefit note if the question names one
        (never for legal advice), otherwise a refusal."""
        reason = state.get("refusal_reason", "")
        if state.get("mentions") and not reason.startswith("legal_advice"):
            return "note_only"
        return "refuse"

    def refused_or(next_node: str):
        return lambda state: failed(state) if state.get("refusal_reason") else next_node

    def after_grounding(state: State) -> str:
        if state.get("refusal_reason"):
            return failed(state)
        return "finalize" if state["grounding"].ok else "generate"

    g = StateGraph(State)
    for name, fn in [
        ("legal_check", legal_check),
        ("retrieve", retrieve),
        ("coverage_gate", coverage_gate),
        ("generate", generate),
        ("check_grounding", check_grounding),
        ("finalize", finalize),
        ("note_only", note_only),
        ("refuse", refuse),
    ]:
        g.add_node(name, fn)
    g.add_edge(START, "legal_check")
    fail = ["note_only", "refuse"]
    g.add_conditional_edges("legal_check", refused_or("retrieve"), ["retrieve", *fail])
    g.add_conditional_edges("retrieve", refused_or("coverage_gate"), ["coverage_gate", *fail])
    g.add_conditional_edges("coverage_gate", refused_or("generate"), ["generate", *fail])
    g.add_conditional_edges("generate", refused_or("check_grounding"), ["check_grounding", *fail])
    g.add_conditional_edges("check_grounding", after_grounding, ["finalize", "generate", *fail])
    g.add_conditional_edges("finalize", refused_or(END), [END, *fail])
    g.add_conditional_edges(
        "note_only", lambda s: END if s.get("answer") else "refuse", [END, "refuse"]
    )
    g.add_edge("refuse", END)
    return g.compile()


def _citation(n: int, hits: list[Hit]) -> Citation:
    p = hits[n - 1].passage
    return Citation(f"S{n}", p.url, p.section, p.fetched_at, p.tags.historical, hits[n - 1].also_on)


def run_graph(
    question: str,
    index: Index,
    llm: LLM,
    glossary: list[Term] | None = None,
    settings: Settings | None = None,
    abolished: list[Abolished] | None = None,
) -> tuple[Answer, list[str]]:
    """Run one question through the graph. Returns the answer and the path it took.

    `abolished=None` loads sources/abolished.toml; pass [] to turn the notes off."""
    graph = build_graph(index, llm, glossary, settings, abolished)
    final = graph.invoke({"question": question, "path": []})
    answer = final["answer"]
    answer.path = final["path"]
    return answer, final["path"]
