"""Run the eval sets and save a dated report per set in evals/reports/.

    python -m jobseeker_assistant.evals                 # golden + held-out, LLM from env
    python -m jobseeker_assistant.evals --set heldout   # one set only
    python -m jobseeker_assistant.evals --sweep         # cutoff table, golden set ONLY

The golden set (evals/golden.yaml) may be used for tuning. The held-out set
(evals/heldout.yaml) never is: it shows whether a change generalises.

Exact checks per case:
- refusal_ok        refused exactly when the case says must_refuse (and, if the case names
                    a refusal_reason, refused for that reason)
- source_cited      the answer cites at least one expected source URL
- facts_in_answer   every key fact appears in the answer text
Diagnostics (why a case failed):
- source_retrieved  an expected source was among the retrieved passages
- facts_in_sources  every key fact appears somewhere in the retrieved passages
A case passes if refusal_ok and, for in-scope cases, source_cited and facts_in_answer.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import yaml

from . import snapshots
from .answer import Answer, answer_question
from .glossary import Term, expand, load_glossary
from .llm import LLM, get_llm
from .retrieve import Hit, Index
from .source_tags import load_tags

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "evals" / "golden.yaml"
HELDOUT = ROOT / "evals" / "heldout.yaml"
REPORTS = ROOT / "evals" / "reports"
CATEGORIES = {"current", "abolished", "tricky", "out_of_scope"}


@dataclass(frozen=True)
class Case:
    id: str
    category: str
    question: str
    must_refuse: bool = False
    key_facts: tuple[str, ...] = ()
    expected_sources: tuple[str, ...] = ()
    refusal_reason: str = ""  # optional: the refusal must come from this rule (prefix match)


def load_golden(path: Path = GOLDEN) -> list[Case]:
    """Load an eval set (golden or held-out; same format)."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    cases, seen = [], set()
    for item in raw:
        case = Case(
            id=item["id"],
            category=item["category"],
            question=item["question"],
            must_refuse=bool(item.get("must_refuse", False)),
            key_facts=tuple(item.get("key_facts", ())),
            expected_sources=tuple(item.get("expected_sources", ())),
            refusal_reason=item.get("refusal_reason", ""),
        )
        if case.id in seen:
            raise ValueError(f"duplicate case id {case.id}")
        seen.add(case.id)
        if case.category not in CATEGORIES:
            raise ValueError(f"{case.id}: unknown category {case.category}")
        if case.refusal_reason and not case.must_refuse:
            raise ValueError(f"{case.id}: refusal_reason only makes sense with must_refuse")
        if case.must_refuse and (case.key_facts or case.expected_sources):
            raise ValueError(f"{case.id}: must_refuse cases have no facts or sources")
        if not case.must_refuse and not (case.key_facts and case.expected_sources):
            raise ValueError(f"{case.id}: in-scope cases need key_facts and expected_sources")
        cases.append(case)
    return cases


def fact_present(fact: str, text: str) -> bool:
    """'a | b' matches if either phrase is in the text (case-insensitive)."""
    text = " ".join(text.lower().split())
    return any(alt.strip().lower() in text for alt in fact.split("|"))


def _urls_of_hit(hit: Hit) -> set[str]:
    return {hit.passage.url, *hit.also_on}


@dataclass
class CaseResult:
    id: str
    category: str
    question: str
    must_refuse: bool
    refused: bool
    refusal_reason: str
    refusal_ok: bool
    source_cited: bool | None
    source_retrieved: bool | None
    facts_in_answer: bool | None
    facts_in_sources: bool | None
    missing_facts: list[str] = field(default_factory=list)
    top_score: float = 0.0
    top_coverage: float = 0.0
    cited_urls: list[str] = field(default_factory=list)
    answer: str = ""
    glossary_used: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        if self.must_refuse:
            return self.refusal_ok
        return bool(self.refusal_ok and self.source_cited and self.facts_in_answer)


def grade(case: Case, ans: Answer, top_score: float, top_coverage: float = 0.0) -> CaseResult:
    refusal_ok = ans.refused == case.must_refuse
    if case.refusal_reason and not ans.refusal_reason.startswith(case.refusal_reason):
        refusal_ok = False  # refused, but not for the reason this case is about
    if case.must_refuse:
        cited = retrieved = in_answer = in_sources = None
        missing: list[str] = []
    else:
        expected = set(case.expected_sources)
        cited_urls = set().union(*({c.url, *c.also_on} for c in ans.citations))
        cited = bool(expected & cited_urls)
        retrieved = bool(expected & set().union(*(_urls_of_hit(h) for h in ans.hits)))
        answer_text = "" if ans.refused else ans.text
        missing = [f for f in case.key_facts if not fact_present(f, answer_text)]
        in_answer = not missing
        source_text = "\n".join(h.passage.text for h in ans.hits)
        in_sources = all(fact_present(f, source_text) for f in case.key_facts)
    return CaseResult(
        id=case.id,
        category=case.category,
        question=case.question,
        must_refuse=case.must_refuse,
        refused=ans.refused,
        refusal_reason=ans.refusal_reason,
        refusal_ok=refusal_ok,
        source_cited=cited,
        source_retrieved=retrieved,
        facts_in_answer=in_answer,
        facts_in_sources=in_sources,
        missing_facts=missing,
        top_score=round(top_score, 3),
        top_coverage=round(top_coverage, 3),
        cited_urls=sorted({c.url for c in ans.citations}),
        answer=ans.text,
    )


def run(
    cases: list[Case],
    index: Index,
    llm: LLM,
    min_score: float | None = None,
    min_coverage: float | None = None,
    glossary: list[Term] | None = None,
):
    kwargs: dict = {"glossary": glossary}
    if min_score is not None:
        kwargs["min_score"] = min_score
    if min_coverage is not None:
        kwargs["min_coverage"] = min_coverage
    results = []
    for case in cases:
        exp = expand(case.question, glossary or [])
        top = index.search(exp.retrieval_query, k=4)
        score = top[0].score if top else 0.0
        cov = max((index.coverage(exp.coverage_query, h.passage) for h in top), default=0.0)
        ans = answer_question(case.question, index, llm, **kwargs)
        result = grade(case, ans, score, cov)
        result.glossary_used = ans.glossary_used
        results.append(result)
    return results


def _rate(values: list[bool | None]) -> str:
    vals = [v for v in values if v is not None]
    return f"{sum(vals)}/{len(vals)}" if vals else "–"


def summarize(results: list[CaseResult]) -> dict:
    in_scope = [r for r in results if not r.must_refuse]
    oos = [r for r in results if r.must_refuse]
    by_cat = {}
    for cat in sorted({r.category for r in results}):
        rs = [r for r in results if r.category == cat]
        by_cat[cat] = _rate([r.passed for r in rs])
    return {
        "passed": _rate([r.passed for r in results]),
        "by_category": by_cat,
        "out_of_scope_refused": _rate([r.refused for r in oos]),
        "in_scope_answered": _rate([not r.refused for r in in_scope]),
        "source_cited": _rate([r.source_cited for r in in_scope]),
        "source_retrieved": _rate([r.source_retrieved for r in in_scope]),
        "facts_in_answer": _rate([r.facts_in_answer for r in in_scope]),
        "facts_in_sources": _rate([r.facts_in_sources for r in in_scope]),
    }


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True
        )
        commit = out.stdout.strip() or "unknown"
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--", "src", "sources", "evals/golden.yaml"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        ).stdout.strip()
        return commit + ("+dirty" if dirty else "")
    except OSError:
        return "unknown"


def _mark(v: bool | None) -> str:
    return "–" if v is None else ("✅" if v else "❌")


def render_markdown(meta: dict, summary: dict, results: list[CaseResult]) -> str:
    lines = [
        f"# Eval report {meta['run_at']}",
        "",
        f"LLM: `{meta['llm']}` · min_score: `{meta['min_score']}`"
        f" · min_coverage: `{meta.get('min_coverage', '–')}` · commit: `{meta['commit']}`"
        f" · cases: {meta['cases']}",
        "",
        "| Metric | Result |",
        "|---|---|",
    ]
    for key, value in summary.items():
        if key != "by_category":
            lines.append(f"| {key} | {value} |")
    for cat, value in summary["by_category"].items():
        lines.append(f"| passed · {cat} | {value} |")
    lines += [
        "",
        "| Case | Category | Pass | Refusal ok | Cited | Retrieved | Facts in answer"
        " | Facts in sources | Top score | Coverage |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r.id} | {r.category} | {_mark(r.passed)} | {_mark(r.refusal_ok)}"
            f" | {_mark(r.source_cited)} | {_mark(r.source_retrieved)}"
            f" | {_mark(r.facts_in_answer)} | {_mark(r.facts_in_sources)} | {r.top_score}"
            f" | {r.top_coverage} |"
        )
    return "\n".join(lines) + "\n"


def save_report(
    results: list[CaseResult], meta: dict, directory: Path = REPORTS
) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    stem = meta["run_at"].replace(":", "").replace("+0000", "Z") + f"_{meta['llm_provider']}"
    if meta.get("label"):
        stem += f"_{meta['label']}"
    base, n = stem, 2
    while (directory / f"{stem}.json").exists():  # never overwrite an earlier run
        stem, n = f"{base}-{n}", n + 1
    summary = summarize(results)
    data = {
        "meta": meta,
        "summary": summary,
        "results": [asdict(r) | {"passed": r.passed} for r in results],
    }
    json_path = directory / f"{stem}.json"
    md_path = directory / f"{stem}.md"
    json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(meta, summary, results), encoding="utf-8")
    return json_path, md_path


def case_signals(
    cases: list[Case], index: Index, k: int = 4, glossary: list[Term] | None = None
) -> dict[str, tuple[float, float]]:
    """Per case: (top BM25 score, best coverage among the top-k passages)."""
    out = {}
    for c in cases:
        exp = expand(c.question, glossary or [])
        hits = index.search(exp.retrieval_query, k=k)
        score = hits[0].score if hits else 0.0
        cov = max((index.coverage(exp.coverage_query, h.passage) for h in hits), default=0.0)
        out[c.id] = (score, cov)
    return out


def sweep(
    cases: list[Case], signals: dict[str, tuple[float, float]], signal: str, cutoffs: list[float]
) -> list[dict]:
    """Retrieval-only: for each cutoff on one signal ("score" or "coverage"), how many
    out-of-scope cases are refused and how many in-scope cases still get through."""
    pos = {"score": 0, "coverage": 1}[signal]
    oos = [c for c in cases if c.must_refuse]
    ins = [c for c in cases if not c.must_refuse]
    rows = []
    for cutoff in cutoffs:
        refused = sum(signals[c.id][pos] < cutoff for c in oos)
        kept = sum(signals[c.id][pos] >= cutoff for c in ins)
        rows.append(
            {
                "signal": signal,
                "cutoff": cutoff,
                "oos_refused": refused,
                "of_oos": len(oos),
                "in_scope_kept": kept,
                "of_in_scope": len(ins),
            }
        )
    return rows


SETS = {"golden": GOLDEN, "heldout": HELDOUT}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-score", type=float, default=None)
    parser.add_argument("--min-coverage", type=float, default=None)
    parser.add_argument("--sweep", action="store_true", help="tuning table (golden set only)")
    parser.add_argument("--set", choices=[*SETS, "both"], default="both")
    parser.add_argument("--no-save", action="store_true")
    parser.add_argument("--no-glossary", action="store_true", help="turn query expansion off")
    parser.add_argument("--label", default="", help="short tag added to the report file name")
    args = parser.parse_args(argv)

    index = Index.from_snapshots(snapshots.load_all(), load_tags())
    glossary = [] if args.no_glossary else load_glossary()
    if args.sweep:
        # Tuning only ever looks at the golden set; the held-out set stays unseen.
        cases = load_golden(GOLDEN)
        signals = case_signals(cases, index, glossary=glossary)
        grids = {"score": [x / 2 for x in range(0, 31)], "coverage": [x / 20 for x in range(21)]}
        for signal, grid in grids.items():
            print(f"\n{signal:>8}  out-of-scope refused  in-scope kept")
            for row in sweep(cases, signals, signal, grid):
                print(
                    f"{row['cutoff']:8.2f}  {row['oos_refused']:>10}/{row['of_oos']}"
                    f"  {row['in_scope_kept']:>12}/{row['of_in_scope']}"
                )
        return 0

    from .answer import DEFAULT_MIN_COVERAGE, DEFAULT_MIN_SCORE

    llm = get_llm()
    provider = os.environ.get("LLM_PROVIDER", "anthropic")
    run_at = datetime.now(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%S%z")
    names = list(SETS) if args.set == "both" else [args.set]
    summaries = {}
    for name in names:
        cases = load_golden(SETS[name])
        results = run(cases, index, llm, args.min_score, args.min_coverage, glossary)
        meta = {
            "run_at": run_at,
            "set": name,
            "llm_provider": provider,
            "llm": provider if provider == "fake" else os.environ.get("LLM_MODEL", "default"),
            "min_score": args.min_score if args.min_score is not None else DEFAULT_MIN_SCORE,
            "min_coverage": (
                args.min_coverage if args.min_coverage is not None else DEFAULT_MIN_COVERAGE
            ),
            "commit": _git_commit(),
            "glossary_terms": len(glossary),
            "cases": len(cases),
            "label": "_".join(x for x in (name, args.label) if x),
        }
        summaries[name] = summarize(results)
        if not args.no_save:
            _, md_path = save_report(results, meta)
            print(f"report: {md_path.relative_to(ROOT)}")
    print(f"\n{'metric':22}" + "".join(f"{n:>12}" for n in names))
    for key in summaries[names[0]]:
        if key == "by_category":
            continue
        print(f"{key:22}" + "".join(f"{summaries[n][key]:>12}" for n in names))
    return 0


if __name__ == "__main__":
    sys.exit(main())
