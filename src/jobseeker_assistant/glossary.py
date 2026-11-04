"""Query expansion from a reviewed glossary (sources/glossary.toml).

People ask with Finnish terms ("palkkatuki") or everyday words ("side gig"); the English
pages say "pay subsidy" and "part-time work". When a glossary term is in the question:
- the search query gets the page wording added (so the right passages are found), and
- the coverage check sees the page wording instead of the term (so a real question isn't
  refused just because the pages never use the Finnish word).
The answer itself still uses only page text: the glossary only changes what is searched.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from . import snapshots

ORIGINS = {"source", "reviewed"}


@dataclass(frozen=True)
class Term:
    match: tuple[str, ...]
    means: tuple[str, ...]
    origin: str
    source: str = ""
    why: str = ""


@dataclass(frozen=True)
class Expansion:
    question: str
    retrieval_query: str
    coverage_query: str
    used: tuple[Term, ...] = field(default_factory=tuple)


def parse_glossary(data: dict) -> list[Term]:
    terms = []
    for i, raw in enumerate(data.get("term", [])):
        unknown = set(raw) - {"match", "means", "origin", "source", "why"}
        if unknown:
            raise ValueError(f"glossary entry {i}: unknown field(s) {sorted(unknown)}")
        t = Term(
            match=tuple(m.lower() for m in raw["match"]),
            means=tuple(raw["means"]),
            origin=raw["origin"],
            source=raw.get("source", ""),
            why=raw.get("why", ""),
        )
        if not t.match or not t.means:
            raise ValueError(f"glossary entry {i}: needs match and means")
        if t.origin not in ORIGINS:
            raise ValueError(f"glossary entry {i}: origin must be one of {sorted(ORIGINS)}")
        if t.origin == "source" and not t.source:
            raise ValueError(f"glossary entry {i} ({t.match[0]}): origin=source needs `source`")
        if t.origin == "reviewed" and not t.why:
            raise ValueError(f"glossary entry {i} ({t.match[0]}): origin=reviewed needs `why`")
        terms.append(t)
    return terms


def load_glossary(path: Path | None = None) -> list[Term]:
    path = path or snapshots.DEFAULT_SOURCES_DIR / "glossary.toml"
    if not path.exists():
        return []
    return parse_glossary(tomllib.loads(path.read_text(encoding="utf-8")))


def _pattern(phrase: str) -> re.Pattern:
    return re.compile(rf"(?<![\wåäö-]){re.escape(phrase)}(?![\wåäö-])", re.IGNORECASE)


def expand(question: str, terms: list[Term]) -> Expansion:
    retrieval_extra: list[str] = []
    coverage_query = question
    used = []
    for term in terms:
        # Longest phrase first, so "side gig" wins over "gig".
        hit = next(
            (m for m in sorted(term.match, key=len, reverse=True) if _pattern(m).search(question)),
            None,
        )
        if hit is None:
            continue
        used.append(term)
        retrieval_extra.extend(term.means)
        coverage_query = _pattern(hit).sub(term.means[0], coverage_query)
    retrieval_query = " ".join([question, *retrieval_extra])
    return Expansion(question, retrieval_query, coverage_query, tuple(used))
