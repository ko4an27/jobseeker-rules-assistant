"""LLM-as-judge: score an answer against the written rubric (evals/judge_rubric.md).

    judge = LLMJudge(get_llm(prefix="JUDGE"))   # real model (make eval-real)
    judge = FakeJudge({"correct": "pass", ...})  # fixed scores, for tests

Seven criteria, each pass / fail / n/a. The code decides n/a where it can (a refusal makes
the answer-content criteria n/a; no abolished benefit named makes replaced_note n/a), so the
judge model is only asked what needs judgement. The judge's agreement with human labels is
checked with `make judge-calibrate` (evals/judge_calibration.yaml).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .llm import LLM

ROOT = Path(__file__).resolve().parents[2]
RUBRIC_PATH = ROOT / "evals" / "judge_rubric.md"
CALIBRATION_PATH = ROOT / "evals" / "judge_calibration.yaml"

CRITERIA = (
    "correct",
    "grounded",
    "right_source",
    "meaning_preserved",
    "plain_language",
    "safe_refusal",
    "replaced_note",
)
VERDICTS = {"pass", "fail", "n/a"}
ANSWER_CONTENT = ("correct", "grounded", "right_source", "meaning_preserved")


@dataclass(frozen=True)
class JudgeInput:
    question: str
    answer: str
    passages: list[tuple[str, str, str]]  # (label "S1", url, text)
    key_facts: tuple[str, ...] = ()
    must_refuse: bool = False
    refused: bool = False
    names_abolished: bool = False


@dataclass
class Verdict:
    scores: dict[str, str] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)
    error: str = ""

    @property
    def passed(self) -> bool:
        return not self.error and all(v != "fail" for v in self.scores.values())

    @property
    def failed_criteria(self) -> list[str]:
        return [c for c, v in self.scores.items() if v == "fail"]


def not_applicable(item: JudgeInput) -> set[str]:
    """Criteria the code marks n/a without asking the judge."""
    na = set()
    if item.refused:
        na.update(ANSWER_CONTENT)
    if item.must_refuse:
        na.add("correct")  # nothing is expected to be stated
    if not item.names_abolished:
        na.add("replaced_note")
    return na


def build_prompt(item: JudgeInput, rubric: str) -> tuple[str, str]:
    na = not_applicable(item)
    ask = [c for c in CRITERIA if c not in na]
    system = (
        "You are a strict evaluator of answers from a public-service assistant. "
        "Judge ONLY against the rubric and the passages given; do not use outside knowledge.\n\n"
        + rubric
        + "\n\nReply with JSON only, no other text: an object with exactly these keys: "
        + ", ".join(ask)
        + '. Each value is {"verdict": "pass" | "fail" | "n/a", "reason": "<one sentence>"}.'
    )
    passages = "\n\n".join(f"[{label}] ({url})\n{text}" for label, url, text in item.passages)
    facts = "\n".join(f"- {f}" for f in item.key_facts) or "(none given)"
    yes = {True: "yes", False: "no"}
    user = (
        f"QUESTION:\n{item.question}\n\n"
        f"MUST BE REFUSED: {yes[item.must_refuse]}\n"
        f"ANSWER REFUSED: {yes[item.refused]}\n"
        f"NAMES AN ABOLISHED BENEFIT OR THE TE OFFICE: {yes[item.names_abolished]}\n\n"
        f"EXPECTED KEY FACTS:\n{facts}\n\n"
        f"PASSAGES GIVEN TO THE ASSISTANT:\n{passages or '(none)'}\n\n"
        f"ANSWER:\n{item.answer}"
    )
    return system, user


def parse_verdict(raw: str, item: JudgeInput) -> Verdict:
    """Parse the judge's JSON. Any problem becomes Verdict.error, never an exception."""
    na = not_applicable(item)
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        return Verdict(error="judge reply had no JSON object")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        return Verdict(error=f"judge reply was not valid JSON: {exc.msg}")
    verdict = Verdict()
    for c in CRITERIA:
        if c in na:
            verdict.scores[c], verdict.reasons[c] = "n/a", "not applicable (decided by code)"
            continue
        entry = data.get(c)
        value = entry.get("verdict") if isinstance(entry, dict) else entry
        value = str(value).strip().lower() if value is not None else ""
        if value not in VERDICTS:
            return Verdict(error=f"judge gave no valid verdict for '{c}'")
        verdict.scores[c] = value
        verdict.reasons[c] = str(entry.get("reason", "")) if isinstance(entry, dict) else ""
    return verdict


class LLMJudge:
    def __init__(self, llm: LLM, rubric: str | None = None):
        self.llm = llm
        self.rubric = rubric if rubric is not None else RUBRIC_PATH.read_text(encoding="utf-8")

    def evaluate(self, item: JudgeInput) -> Verdict:
        system, user = build_prompt(item, self.rubric)
        return parse_verdict(self.llm.complete(system, user), item)


class FakeJudge:
    """Fixed scores for tests: FakeJudge({"correct": "fail"}) -> everything else passes.
    Or FakeJudge(func) where func(item) returns a dict of scores."""

    def __init__(self, scores: dict[str, str] | Callable[[JudgeInput], dict] | None = None):
        self.scores = scores or {}
        self.items: list[JudgeInput] = []

    def evaluate(self, item: JudgeInput) -> Verdict:
        self.items.append(item)
        given = self.scores(item) if callable(self.scores) else self.scores
        na = not_applicable(item)
        scores = {c: "n/a" if c in na else given.get(c, "pass") for c in CRITERIA}
        return Verdict(scores=scores, reasons={c: "fake judge" for c in CRITERIA})


# --- Calibration: does the judge agree with human labels? ------------------------------


@dataclass(frozen=True)
class CalibrationExample:
    id: str
    item: JudgeInput
    labels: dict[str, str]
    why: str = ""


def load_calibration(path: Path = CALIBRATION_PATH) -> tuple[list[CalibrationExample], bool]:
    """Returns (examples, reviewed): `reviewed` is false until a human confirms the labels."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    examples = []
    for raw in data["examples"]:
        item = JudgeInput(
            question=raw["question"],
            answer=raw["answer"],
            passages=[tuple(p) for p in raw.get("passages", [])],
            key_facts=tuple(raw.get("key_facts", ())),
            must_refuse=bool(raw.get("must_refuse", False)),
            refused=bool(raw.get("refused", False)),
            names_abolished=bool(raw.get("names_abolished", False)),
        )
        labels = {c: str(v).lower() for c, v in raw["labels"].items()}
        if set(labels) != set(CRITERIA) or not set(labels.values()) <= VERDICTS:
            raise ValueError(f"{raw['id']}: labels must give pass/fail/n/a for every criterion")
        for c in not_applicable(item):
            if labels[c] != "n/a":
                raise ValueError(f"{raw['id']}: '{c}' is n/a by rule, label says {labels[c]}")
        examples.append(CalibrationExample(raw["id"], item, labels, raw.get("why", "")))
    return examples, bool(data.get("reviewed", False))


def calibrate(judge, examples: list[CalibrationExample]) -> dict:
    """Agreement per criterion, counting only criteria the judge actually decided
    (n/a-by-rule criteria agree automatically and would inflate the number)."""
    per: dict[str, list[bool]] = {c: [] for c in CRITERIA}
    overall: list[bool] = []
    disagreements, errors = [], []
    for ex in examples:
        verdict = judge.evaluate(ex.item)
        if verdict.error:
            errors.append({"id": ex.id, "error": verdict.error})
            overall.append(False)  # a judge error never counts as agreement
            continue
        decided = set(CRITERIA) - not_applicable(ex.item)
        label_pass = all(ex.labels[c] != "fail" for c in CRITERIA)
        overall.append(label_pass == verdict.passed)
        for c in decided:
            agree = verdict.scores.get(c) == ex.labels[c]
            per[c].append(agree)
            if not agree:
                disagreements.append(
                    {
                        "id": ex.id,
                        "criterion": c,
                        "label": ex.labels[c],
                        "judge": verdict.scores.get(c),
                        "judge_reason": verdict.reasons.get(c, ""),
                    }
                )
    all_votes = [v for votes in per.values() for v in votes]
    return {
        "overall_agreement": f"{sum(overall)}/{len(overall)}",
        "agreement": f"{sum(all_votes)}/{len(all_votes)}",
        "agreement_rate": round(sum(all_votes) / len(all_votes), 3) if all_votes else None,
        "by_criterion": {c: f"{sum(v)}/{len(v)}" for c, v in per.items() if v},
        "disagreements": disagreements,
        "errors": errors,
    }
