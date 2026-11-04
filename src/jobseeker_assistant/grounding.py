"""Grounding self-check: is every claim in a draft answer supported by its cited passage?

Runs in code, without another LLM call, so it is cheap, repeatable and testable offline.
A "claim" is a sentence of the answer. For each claim:

1. It must cite at least one source it was given ([S1]...), unless it is too short to
   state a fact (e.g. "Yes.").
2. Every number in it (37.21, 50%, 2026, 7) must appear in the cited passages.
3. At least MIN_WORD_SUPPORT of its key words must appear in the cited passages
   (light stemming, so "lasts" matches "last").

This catches invented numbers, invented or missing citations and claims about things the
cited text never mentions. It does not understand meaning: a paraphrase with new words may
fail, and a sentence that reuses the source's words but says something different may pass.
An LLM judge with a written rubric (planned next) covers that; this is the first line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .retrieve import Hit, tokenize

MIN_WORD_SUPPORT = 0.6
MIN_FACT_WORDS = 3  # sentences with fewer key words and no number are not treated as claims

_CITATION = re.compile(r"\[S(\d+)\]")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
# Words that carry no fact of their own in an answer sentence.
_FILLER = set(
    "also get got gets just only so then than however yes no not need needs must may might "
    "should would could usually generally means mean like".split()
)


@dataclass(frozen=True)
class ClaimCheck:
    claim: str
    supported: bool
    reason: str = ""  # why not: "no citation", "invented citation [S9]", "number 42 not in source"
    word_support: float = 1.0


@dataclass
class GroundingResult:
    checks: list[ClaimCheck] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.supported for c in self.checks) and bool(self.checks)

    @property
    def unsupported(self) -> list[ClaimCheck]:
        return [c for c in self.checks if not c.supported]


def stem(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


_SENTENCE = re.compile(r".+?(?:[.!?](?:\[S\d+\])*(?=\s|$)|$)")


def split_claims(answer: str) -> list[str]:
    """Sentences of the answer. Citations right after a full stop stay with their sentence
    ("fact. [S1]" -> "fact.[S1]"), and decimals like 37.21 don't end a sentence."""
    text = " ".join(answer.split())
    text = re.sub(r"([.!?])\s+((?:\[S\d+\])+)", r"\1\2", text)
    return [m.group(0).strip() for m in _SENTENCE.finditer(text) if m.group(0).strip()]


def _numbers(text: str) -> set[str]:
    return {n.replace(",", ".") for n in _NUMBER.findall(text)}


def check_claim(claim: str, hits: list[Hit]) -> ClaimCheck:
    labels = [int(n) for n in _CITATION.findall(claim)]
    plain = _CITATION.sub("", claim)
    words = [w for w in tokenize(plain) if w not in _FILLER and not w.isdigit()]
    numbers = _numbers(plain)
    if not labels:
        if numbers or len(words) >= MIN_FACT_WORDS:
            return ClaimCheck(claim, False, "no citation")
        return ClaimCheck(claim, True, "not a factual claim")
    bad = [n for n in labels if n < 1 or n > len(hits)]
    if bad:
        return ClaimCheck(claim, False, "invented citation " + " ".join(f"[S{n}]" for n in bad))

    cited = [hits[n - 1].passage for n in labels]
    source_text = " ".join(f"{p.title} {p.section} {p.text}" for p in cited)
    missing_numbers = sorted(numbers - _numbers(source_text))
    if missing_numbers:
        return ClaimCheck(claim, False, f"number {', '.join(missing_numbers)} not in source")
    if not words:
        return ClaimCheck(claim, True)
    source_words = {stem(w) for w in tokenize(source_text)}
    support = sum(stem(w) in source_words for w in words) / len(words)
    if support < MIN_WORD_SUPPORT:
        return ClaimCheck(claim, False, f"only {support:.0%} of key words in source", support)
    return ClaimCheck(claim, True, word_support=support)


def check_answer(answer: str, hits: list[Hit]) -> GroundingResult:
    checks = [check_claim(c, hits) for c in split_claims(answer)]
    if not any(_CITATION.search(c.claim) for c in checks):
        # An answer must make at least one cited claim; "Yes." alone checks nothing.
        checks.append(ClaimCheck(answer.strip(), False, "no cited claim in the answer"))
    return GroundingResult(checks)
