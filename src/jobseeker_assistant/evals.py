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
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import yaml

from . import snapshots
from .abolished import load_abolished, mentioned
from .answer import Answer, answer_question
from .budget import (
    Budget,
    BudgetExceeded,
    GuardedLLM,
    ResponseCache,
    estimate_cost,
    format_cost,
    max_calls_from_env,
    prices_for,
)
from .dotenv import load_dotenv
from .glossary import Term, expand, load_glossary
from .judge import (
    CALIBRATION_PATH,
    CRITERIA,
    JudgeInput,
    LLMJudge,
    Verdict,
    calibrate,
    load_calibration,
)
from .llm import LLM, ProviderError, get_llm
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


_NUMBER_WORDS = {
    word: str(n)
    for n, word in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
        "fifteen sixteen seventeen eighteen nineteen twenty".split()
    )
} | {"thirty": "30", "forty": "40", "fifty": "50", "sixty": "60", "hundred": "100"}
_NUMBER_WORD_RE = re.compile(r"\b(" + "|".join(_NUMBER_WORDS) + r")\b")
_UNIT_PLURAL_RE = re.compile(r"\b(day|week|month|year|hour)s\b")


def normalise(text: str) -> str:
    """Lower case, single spaces, number words as digits ("two" -> "2"), so a key fact like
    "2 study programmes" is found in "at least two study programmes". Applied to both the
    expected fact and the answer, for golden and held-out alike (added after the first real
    eval, 2026-11-05: a correct answer said "two" where the label said "2").

    Also (added 2026-11-06, after seeing held-out results: "a 2-week period" vs "2 weeks"):
    a number joined to a word by a hyphen is split ("2-week" -> "2 week", "two-week" -> "2 week"),
    and time units are made singular ("weeks" -> "week"), on both sides, so plural, singular and
    hyphenated forms match. Hyphens between letters ("e-service") are left alone."""
    text = " ".join(text.lower().split())
    text = _NUMBER_WORD_RE.sub(lambda m: _NUMBER_WORDS[m.group(1)], text)
    text = re.sub(r"(\d)-(?=[a-z])", r"\1 ", text)
    return _UNIT_PLURAL_RE.sub(lambda m: m.group(1), text)


def fact_present(fact: str, text: str) -> bool:
    """'a | b' matches if either phrase is in the text (case-insensitive, number words = digits)."""
    text = normalise(text)
    # A fact must start at a word boundary ("6 months" is not in "16 months"); its end may run
    # on, so plurals still match ("e-service" in "e-services").
    return any(
        re.search(r"(?<!\w)" + re.escape(normalise(alt.strip())), text) for alt in fact.split("|")
    )


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
    attempts: int = 0  # LLM calls; 2 means the grounding check sent it back once
    path: list[str] = field(default_factory=list)
    judge: dict | None = None  # {"scores": {criterion: pass|fail|n/a}, "reasons", "error"}

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
    judge=None,
    into: list[CaseResult] | None = None,
):
    """Answer and grade every case; with `judge`, also score each answer against the rubric.
    Results are appended to `into` as they come, so a run stopped by the budget keeps them."""
    kwargs: dict = {"glossary": glossary}
    if min_score is not None:
        kwargs["min_score"] = min_score
    if min_coverage is not None:
        kwargs["min_coverage"] = min_coverage
    results = into if into is not None else []
    abolished = load_abolished() if judge else []
    for case in cases:
        exp = expand(case.question, glossary or [])
        top = index.search(exp.retrieval_query, k=4)
        score = top[0].score if top else 0.0
        cov = max((index.coverage(exp.coverage_query, h.passage) for h in top), default=0.0)
        ans = answer_question(case.question, index, llm, **kwargs)
        result = grade(case, ans, score, cov)
        result.glossary_used = ans.glossary_used
        result.attempts = ans.attempts
        result.path = ans.path
        if judge is not None:
            try:
                verdict = judge.evaluate(
                    judge_input(case, ans, bool(mentioned(case.question, abolished)))
                )
            except ProviderError as exc:  # judge model unavailable (e.g. 503 after retries)
                verdict = Verdict(error=f"judge unavailable: {exc}"[:300])
            result.judge = {
                "scores": verdict.scores,
                "reasons": verdict.reasons,
                "error": verdict.error,
            }
        results.append(result)
    return results


def judge_input(case: Case, ans: Answer, names_abolished: bool) -> JudgeInput:
    return JudgeInput(
        question=case.question,
        answer=ans.text,
        passages=[(f"S{i}", h.passage.url, h.passage.text) for i, h in enumerate(ans.hits, 1)],
        key_facts=case.key_facts,
        must_refuse=case.must_refuse,
        refused=ans.refused,
        names_abolished=names_abolished,
    )


def judge_summary(results: list[CaseResult]) -> dict:
    """Overall verdict first (an answer passes only if every applicable check passes; a judge
    error counts as not passed), then each check: passes / answers where it applied."""
    judged = [r.judge for r in results if r.judge]
    if not judged:
        return {}
    overall = sum(not j["error"] and all(v != "fail" for v in j["scores"].values()) for j in judged)
    out = {"judge_overall": f"{overall}/{len(judged)}"}
    for c in CRITERIA:
        applied = [j["scores"].get(c) for j in judged if j["scores"].get(c) in ("pass", "fail")]
        out[f"judge_{c}"] = f"{applied.count('pass')}/{len(applied)}" if applied else "–"
    out["judge_errors"] = f"{sum(bool(j['error']) for j in judged)}/{len(judged)}"
    return out


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
        "retried": f"{sum(r.attempts > 1 for r in results)}/{len(results)}",
        "refused_not_grounded": f"{sum(r.refusal_reason == 'not_grounded' for r in results)}"
        f"/{len(results)}",
        **judge_summary(results),
    }


# Everything that shapes an answer or a verdict. Reports are deliberately not in it.
CACHE_INPUTS = (
    "src",
    "sources",
    "evals/golden.yaml",
    "evals/heldout.yaml",
    "evals/judge_rubric.md",
    "evals/judge_calibration.yaml",
)


def code_fingerprint(root: Path | None = None) -> str | None:
    """Cache key part: git's content hashes of CACHE_INPUTS at HEAD, combined.

    Unlike the commit hash, it does not change when only reports are committed (on 2026-11-06
    a reports-only commit made the cache miss and every answer was regenerated). None if any
    of the inputs has uncommitted changes: then a cached answer could hide a change.
    """
    root = root or ROOT
    try:
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--", *CACHE_INPUTS],
            cwd=root,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if dirty:
            return None
        hashes = []
        for path in CACHE_INPUTS:
            out = subprocess.run(
                ["git", "rev-parse", f"HEAD:{path}"], cwd=root, capture_output=True, text=True
            )
            hashes.append(f"{path}={out.stdout.strip() or 'missing'}")
    except OSError:
        return None
    return hashlib.sha256("\n".join(hashes).encode()).hexdigest()[:16]


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True
        )
        commit = out.stdout.strip() or "unknown"
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--", *CACHE_INPUTS],
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
    ]
    if meta.get("aborted"):
        lines += [f"**ABORTED:** {meta['aborted']} — results below are partial.", ""]
    if meta.get("self_judged"):
        lines += [
            f"**Note:** the judge (`{meta['judge']}`) is the same model that wrote the answers, "
            "so judge scores may be lenient. Set JUDGE_MODEL to a different model.",
            "",
        ]
    if meta.get("budget"):
        b = meta["budget"]
        lines += [
            f"Model calls: {b['calls']} (+{b['cache_hits']} from cache) of max {b['max_calls']}"
            f" · tokens in/out: {b['input_tokens']}/{b['output_tokens']}"
            f" · cost: {meta.get('cost_text', b['cost_usd'])}",
            "",
        ]
    lines += [
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
    judged = [r for r in results if r.judge]
    if judged:
        lines += [
            "",
            "## Judge",
            "",
            "| Case | Failed criteria | Judge's reasons |",
            "|---|---|---|",
        ]
        for r in judged:
            if r.judge["error"]:
                lines.append(f"| {r.id} | judge error | {r.judge['error']} |")
                continue
            failed = [c for c, v in r.judge["scores"].items() if v == "fail"]
            why = "; ".join(f"{c}: {r.judge['reasons'].get(c, '')}" for c in failed)
            lines.append(f"| {r.id} | {', '.join(failed) or '—'} | {why.replace('|', '/')} |")
    return "\n".join(lines) + "\n"


def save_report(
    results: list[CaseResult], meta: dict, directory: Path | None = None
) -> tuple[Path, Path]:
    directory = directory or REPORTS  # looked up at call time, so tests can redirect it
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
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-score", type=float, default=None)
    parser.add_argument("--min-coverage", type=float, default=None)
    parser.add_argument("--sweep", action="store_true", help="tuning table (golden set only)")
    parser.add_argument("--set", choices=[*SETS, "both"], default="both")
    parser.add_argument("--no-save", action="store_true")
    parser.add_argument("--no-glossary", action="store_true", help="turn query expansion off")
    parser.add_argument("--label", default="", help="short tag added to the report file name")
    parser.add_argument(
        "--real", action="store_true", help="real model + LLM judge (make eval-real)"
    )
    parser.add_argument("--judge-calibrate", action="store_true", help="judge vs hand labels")
    parser.add_argument(
        "--regrade", type=Path, help="re-score a saved report with the current checker"
    )
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

    if args.regrade:
        report = json.loads(args.regrade.read_text(encoding="utf-8"))
        result = regrade(report, load_golden(SETS[report["meta"]["set"]]))
        print(f"{report['meta']['set']}: passed before {result['before']}, after {result['after']}")
        for c in result["changed"]:
            print(f"  {c['id']}: {c['before']} -> {c['after']}")
        return 0
    if args.judge_calibrate:
        return judge_calibrate_main(args)
    if args.real:
        return real_main(args, index, glossary)

    llm = get_llm()
    provider = os.environ.get("LLM_PROVIDER", "anthropic")
    summaries = evaluate_sets(args, index, llm, glossary, provider)
    print_summaries(summaries)
    return 0


def _meta(args, name: str, cases: int, provider: str, model: str, glossary, run_at: str) -> dict:
    from .answer import DEFAULT_MIN_COVERAGE, DEFAULT_MIN_SCORE

    return {
        "run_at": run_at,
        "set": name,
        "llm_provider": provider,
        "llm": model,
        "min_score": args.min_score if args.min_score is not None else DEFAULT_MIN_SCORE,
        "min_coverage": args.min_coverage
        if args.min_coverage is not None
        else DEFAULT_MIN_COVERAGE,
        "commit": _git_commit(),
        "glossary_terms": len(glossary),
        "cases": cases,
        "label": "_".join(x for x in (name, args.label) if x),
    }


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%S%z")


def evaluate_sets(args, index, llm, glossary, provider, judge=None, budget=None) -> dict:
    """Run the chosen sets; save one report per set. Returns {set: summary}.
    With a budget, a BudgetExceeded stops the run: what was done is saved, marked aborted,
    and the error is re-raised for the caller to report."""
    run_at = _now()
    names = list(SETS) if args.set == "both" else [args.set]
    model = provider if provider == "fake" else getattr(llm, "model", "default")
    summaries: dict = {}
    for name in names:
        cases = load_golden(SETS[name])
        results: list[CaseResult] = []
        aborted = ""
        try:
            run(cases, index, llm, args.min_score, args.min_coverage, glossary, judge, results)
        except BudgetExceeded as exc:
            aborted = str(exc)
        except ProviderError as exc:  # the answering model is unavailable: stop, keep results
            aborted = f"answering model unavailable: {exc}"[:300]
        meta = _meta(args, name, len(cases), provider, model, glossary, run_at)
        if judge is not None:
            meta["judge"] = getattr(getattr(judge, "llm", None), "model", type(judge).__name__)
            meta["self_judged"] = is_self_judged(llm, judge)
        if budget is not None:
            meta["budget"] = budget.summary()
            meta["cost_text"] = format_cost(budget.cost)
        if aborted:
            meta["aborted"] = f"{aborted} (stopped after {len(results)}/{len(cases)} cases)"
        summaries[name] = summarize(results) if results else {}
        if not args.no_save:
            _, md_path = save_report(results, meta)
            print(f"report: {md_path.relative_to(ROOT)}")
        if aborted:
            raise BudgetExceeded(meta["aborted"])
    return summaries


# The judge writes a JSON verdict with a reason per check; thinking models (gemini-3.6-flash
# used 276 thinking tokens for a five-word reply on 2026-11-05) can spend much of an 800-token
# cap before writing it, cutting the JSON off. Answers keep their own, smaller cap.
JUDGE_MAX_TOKENS = 2000


def judge_model_from_env(env: dict | None = None):
    llm = get_llm(env, prefix="JUDGE")
    if hasattr(llm, "max_tokens"):
        llm.max_tokens = max(llm.max_tokens, JUDGE_MAX_TOKENS)
    return llm


def is_self_judged(answer_llm, judge) -> bool:
    """True if the judge runs on the same provider and model as the answering model."""
    judge_llm = getattr(judge, "llm", None)
    if judge_llm is None:
        return False

    def ident(m):
        return (getattr(m, "provider", None), getattr(m, "model", None))

    return ident(answer_llm) == ident(judge_llm) and ident(answer_llm) != (None, None)


def regrade(report: dict, cases: list[Case]) -> dict:
    """Re-score a saved report's answers with the CURRENT fact checker (no model calls).

    Used to show the effect of a checker change on results already seen: only
    facts_in_answer (and so `passed`) can change; answers, citations and refusals are as saved.
    """
    by_id = {c.id: c for c in cases}
    before = after = 0
    changed = []
    for r in report["results"]:
        case = by_id[r["id"]]
        if case.must_refuse:
            ok = bool(r["refusal_ok"])
            before += r["passed"]
            after += ok
            continue
        text = "" if r["refused"] else r["answer"]
        facts_ok = all(fact_present(f, text) for f in case.key_facts)
        ok = bool(r["refusal_ok"] and r["source_cited"] and facts_ok)
        before += r["passed"]
        after += ok
        if ok != r["passed"]:
            changed.append({"id": r["id"], "before": r["passed"], "after": ok})
    n = len(report["results"])
    return {"before": f"{before}/{n}", "after": f"{after}/{n}", "changed": changed}


def print_summaries(summaries: dict) -> None:
    names = [n for n in summaries if summaries[n]]
    if not names:
        return
    print(f"\n{'metric':22}" + "".join(f"{n:>12}" for n in names))
    for key in summaries[names[0]]:
        if key == "by_category":
            continue
        print(f"{key:22}" + "".join(f"{summaries[n].get(key, '–'):>12}" for n in names))


def _guard(llm, budget: Budget, cache: ResponseCache, role: str) -> GuardedLLM:
    return GuardedLLM(llm, budget, cache, code_fingerprint() or "uncommitted", role=role)


def real_main(args, index, glossary) -> int:
    """make eval-real: golden + held-out with the real provider and the LLM judge."""
    provider = os.environ.get("LLM_PROVIDER", "anthropic").strip().lower()
    if provider == "fake":
        print(
            "eval-real needs a real model: set LLM_PROVIDER (gemini, groq or anthropic) "
            "and LLM_API_KEY in .env. For the free offline eval use `make eval`."
        )
        return 2
    try:
        answer_llm, judge_llm = get_llm(), judge_model_from_env()
    except (RuntimeError, ValueError) as exc:
        print(f"not configured: {exc}")
        return 2
    budget = Budget(max_calls_from_env())
    cache = ResponseCache(enabled=code_fingerprint() is not None)
    if not cache.enabled:
        print("note: uncommitted changes, so the response cache is off for this run")
    answer, judge_model = (
        _guard(answer_llm, budget, cache, "answer"),
        _guard(judge_llm, budget, cache, "judge"),
    )
    return run_real(args, index, glossary, answer, LLMJudge(judge_model), budget)


def run_real(args, index, glossary, answer_llm, judge, budget: Budget) -> int:
    names = list(SETS) if args.set == "both" else [args.set]
    n_cases = sum(len(load_golden(SETS[n])) for n in names)
    worst = n_cases * 3  # up to 2 answer calls (retry) + 1 judge call per case
    prices = getattr(answer_llm, "prices", prices_for("fake"))
    print(
        f"plan: {n_cases} cases, at most {min(worst, budget.max_calls)} model calls "
        f"(limit {budget.max_calls}), estimated max cost "
        f"{format_cost(estimate_cost(prices, min(worst, budget.max_calls)))}"
    )
    provider = getattr(answer_llm, "provider", "unknown")
    if is_self_judged(answer_llm, judge):
        print(
            f"WARNING: the judge is the same model as the answerer ({answer_llm.model}), so it "
            "grades its own answers and may be lenient. Set JUDGE_MODEL (e.g. gemini-3.7-flash) "
            "or JUDGE_PROVIDER to use a different judge."
        )
    try:
        summaries = evaluate_sets(args, index, answer_llm, glossary, provider, judge, budget)
    except (BudgetExceeded, ProviderError) as exc:
        print(f"\nABORTED: {exc}")
        print(
            f"calls: {budget.calls}, cache hits: {budget.cache_hits}, "
            f"cost: {format_cost(budget.cost)}"
        )
        return 3
    print_summaries(summaries)
    print(
        f"\ncalls: {budget.calls} (+{budget.cache_hits} cached) of max {budget.max_calls}; "
        f"tokens in/out {budget.input_tokens}/{budget.output_tokens}; "
        f"cost {format_cost(budget.cost)}"
    )
    return 0


def judge_calibrate_main(args) -> int:
    """make judge-calibrate: does the judge agree with the hand labels?"""
    try:
        judge_llm = judge_model_from_env()
    except (RuntimeError, ValueError) as exc:
        print(f"not configured: {exc}")
        return 2
    budget = Budget(max_calls_from_env())
    cache = ResponseCache(enabled=code_fingerprint() is not None)
    judge = LLMJudge(_guard(judge_llm, budget, cache, "judge"))
    return run_calibration(args, judge, budget)


def run_calibration(args, judge, budget: Budget | None = None, path: Path | None = None) -> int:
    examples, reviewed = load_calibration(path or CALIBRATION_PATH)
    if not reviewed:
        print(
            "WARNING: evals/judge_calibration.yaml is not marked reviewed: the labels are a "
            "draft. Agreement with unreviewed labels proves little."
        )
    try:
        result = calibrate(judge, examples)
    except BudgetExceeded as exc:
        print(f"ABORTED: {exc}")
        return 3
    print(f"overall verdict agreement (pass/fail per answer): {result['overall_agreement']}")
    print(f"per-check agreement: {result['agreement']} ({result['agreement_rate']})")
    for c, v in result["by_criterion"].items():
        print(f"  {c:16} {v}")
    for d in result["disagreements"]:
        print(
            f"  disagree {d['id']} {d['criterion']}: label={d['label']} judge={d['judge']} "
            f"({d['judge_reason']})"
        )
    for e in result["errors"]:
        print(f"  judge error {e['id']}: {e['error']}")
    if not args.no_save:
        REPORTS.mkdir(parents=True, exist_ok=True)
        model = getattr(getattr(judge, "llm", None), "model", type(judge).__name__)
        stem = f"{_now().replace(':', '').replace('+0000', 'Z')}_judge-calibration_{model}"
        data = {
            "run_at": _now(),
            "judge": model,
            "labels_reviewed": reviewed,
            "commit": _git_commit(),
            **result,
        }
        if budget is not None:
            data["budget"] = budget.summary()
        out = REPORTS / f"{stem}.json"
        out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"report: {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
