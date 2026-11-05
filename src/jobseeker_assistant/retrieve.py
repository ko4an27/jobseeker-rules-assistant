"""Find the passages most relevant to a question (BM25 keyword search).

Each snapshot is cut into passages at its section headings, so a citation can point to
"URL + section". BM25 is a classic, transparent ranking formula: a passage scores high if
it contains the question's words, especially rare ones. No embeddings or API needed yet.

Each passage's score is multiplied by a weight (see `passage_weight`):
- historical pages rank below current ones (HISTORICAL_WEIGHT),
- sections that are mostly "[link]" lines are excluded or down-weighted,
- a page's own `weight` tag (sources/tags.toml) applies on top.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, replace

from .snapshots import LINK_MARK, Snapshot
from .source_tags import DEFAULT_TAGS, SourceTags

MAX_PASSAGE_CHARS = 1200
HISTORICAL_WEIGHT = 0.5  # prefer current pages
MAX_LINK_SHARE = 0.6  # sections with more link lines than this are left out of retrieval

_STOPWORDS = set(
    "a an and are as at be by can do does for from how i if in is it my of on or the to "
    "what when where which who will with you your me am this that there".split()
)

# Conversational words that say HOW someone asks, not WHAT about. Ignored by the coverage
# check only (search ranking is unchanged). Without this, words like "got", "small" or
# "happened" are rare in the formal pages, so they weighed as much as an off-topic word like
# "pizza" and real questions were refused. Chosen on the golden set (2026-11-04).
COVERAGE_IGNORE = set(
    # leftovers of contractions: can't -> can t, I'm -> i m, you'll -> you ll
    "t s m ll ve d re "
    # filler and discourse words
    "all any even just really still now also ever yet true actually anyway please ok okay "
    "hi hello thanks thank something anything thing things kind sort bit "
    # generic verbs of asking and having
    "got get gets getting lose loses losing happen happened happens know tell want "
    # vague size words
    "small little big lot lots much many some".split()
)


@dataclass(frozen=True)
class Passage:
    id: str
    url: str
    title: str
    section: str
    text: str
    fetched_at: str
    tags: SourceTags = DEFAULT_TAGS

    @property
    def link_share(self) -> float:
        """Fraction of the passage's lines that are just links."""
        lines = [line for line in self.text.splitlines() if line.strip()]
        if not lines:
            return 0.0
        return sum(LINK_MARK in line for line in lines) / len(lines)


def passage_weight(p: Passage) -> float:
    """How much to trust this passage in ranking (0 = never retrieved)."""
    if p.link_share > MAX_LINK_SHARE:
        return 0.0
    weight = p.tags.weight * (1 - p.link_share)
    if p.tags.historical:
        weight *= HISTORICAL_WEIGHT
    return weight


@dataclass(frozen=True)
class Hit:
    passage: Passage
    score: float
    also_on: tuple[str, ...] = ()  # other pages that carry the exact same text


def dedupe_key(text: str) -> str:
    return " ".join(text.lower().split())


def merge_tags(copies: list[Passage]) -> SourceTags:
    """Tags for a passage whose text appears on several pages.

    - "for employers" if any copy is on an employer page (the warning must not get lost);
    - historical only if every copy is on a historical page (if a current page still
      publishes the text, it is current); replaced_by/note come from a historical copy.
    """
    tags = [p.tags for p in copies]
    if all(t.historical for t in tags):
        base = tags[0]
    else:
        base = next(t for t in tags if not t.historical)
    if any(t.audience == "employer" for t in tags):
        base = replace(base, audience="employer")
    return base


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-zåäö0-9]+", text.lower())
    return [w for w in words if w not in _STOPWORDS]


def _split_long(text: str, limit: int = MAX_PASSAGE_CHARS) -> list[str]:
    parts, current = [], ""
    for para in text.split("\n"):
        if current and len(current) + len(para) + 1 > limit:
            parts.append(current)
            current = para
        else:
            current = f"{current}\n{para}" if current else para
    if current.strip():
        parts.append(current)
    return parts


def chunk_snapshot(
    snap: Snapshot, tags: SourceTags = DEFAULT_TAGS, max_chars: int = MAX_PASSAGE_CHARS
) -> list[Passage]:
    """Split a snapshot into passages, one per section (long sections split further)."""
    sections: list[tuple[str, list[str]]] = [(snap.title or "Introduction", [])]
    for line in snap.body.splitlines():
        m = re.match(r"^#{1,4}\s+(.*)", line)
        if m:
            sections.append((m.group(1).strip(), []))
        elif line.strip():
            sections[-1][1].append(line.strip())

    passages = []
    for section, lines in sections:
        if not lines:
            continue
        for part in _split_long("\n".join(lines), max_chars):
            pid = f"{snap.url}#{len(passages)}"
            passages.append(
                Passage(pid, snap.url, snap.title, section, part, snap.fetched_at, tags)
            )
    return passages


class Index:
    """In-memory BM25 index over all passages."""

    def __init__(self, passages: list[Passage], k1: float = 1.5, b: float = 0.75):
        self.passages = passages
        self.k1, self.b = k1, b
        # Section heading words count too: they often name the topic.
        self._docs = [Counter(tokenize(p.section + " " + p.text)) for p in passages]
        self._weights = [passage_weight(p) for p in passages]
        self._lengths = [sum(d.values()) for d in self._docs]
        self._avg_len = (sum(self._lengths) / len(self._lengths)) if passages else 0.0
        df: Counter[str] = Counter()
        for d in self._docs:
            df.update(d.keys())
        n = len(passages)
        self._idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self._max_idf = max(self._idf.values(), default=1.0)
        self._doc_of = {p.id: d for p, d in zip(passages, self._docs, strict=True)}
        # Identical text on several pages (e.g. shared service cards) is one passage for ranking.
        self._groups: dict[str, list[int]] = {}
        for i, p in enumerate(passages):
            self._groups.setdefault(dedupe_key(p.text), []).append(i)

    @classmethod
    def from_snapshots(
        cls,
        snaps: list[Snapshot],
        tags: dict[str, SourceTags] | None = None,
        max_chars: int = MAX_PASSAGE_CHARS,
    ) -> Index:
        tags = tags or {}
        return cls(
            [p for s in snaps for p in chunk_snapshot(s, tags.get(s.url, DEFAULT_TAGS), max_chars)]
        )

    def best_from_url(self, url: str, query: str) -> Hit | None:
        """Best passage from one page, e.g. to bring in the page that replaced a historical one."""
        hits = [
            h
            for h in self.search(query, k=len(self.passages), dedupe=False)
            if h.passage.url == url
        ]
        if hits:
            return hits[0]
        first = next((p for p in self.passages if p.url == url), None)
        return Hit(first, 0.0) if first else None

    def coverage(self, query: str, passage: Passage) -> float:
        """Share of the question a passage matches, 0..1, with rare words counting more.

        Words the sources never use at all (e.g. "pizza") count as the rarest words, so an
        off-topic question gets low coverage even if one common word matches strongly.
        This is a better "is this question covered?" signal than the raw BM25 score, which
        grows with question length.
        """
        terms = set(tokenize(query)) - COVERAGE_IGNORE
        if not terms:
            return 0.0
        doc = self._doc_of.get(passage.id)
        if doc is None:
            doc = Counter(tokenize(passage.section + " " + passage.text))
        weight = {t: self._idf.get(t, self._max_idf) for t in terms}
        return sum(w for t, w in weight.items() if doc.get(t)) / sum(weight.values())

    def search(self, query: str, k: int = 4, dedupe: bool = True) -> list[Hit]:
        terms = set(tokenize(query))
        hits: list[Hit] = []
        rows = zip(self.passages, self._docs, self._lengths, self._weights, strict=True)
        for passage, doc, length, weight in rows:
            if weight == 0:
                continue
            score = 0.0
            for t in terms:
                tf = doc.get(t, 0)
                if tf:
                    norm = tf + self.k1 * (1 - self.b + self.b * length / self._avg_len)
                    score += self._idf[t] * tf * (self.k1 + 1) / norm
            if score > 0:
                hits.append(Hit(passage, score * weight))
        if dedupe:
            hits = self._dedupe(hits)
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:k]

    def _dedupe(self, hits: list[Hit]) -> list[Hit]:
        """Keep the best-scoring copy of each identical text, with tags merged from all copies."""
        best: dict[str, Hit] = {}
        for h in hits:
            key = dedupe_key(h.passage.text)
            if key not in best or h.score > best[key].score:
                best[key] = h
        out = []
        for key, h in best.items():
            copies = [self.passages[i] for i in self._groups[key]]
            if len(copies) == 1:
                out.append(h)
                continue
            others = tuple(sorted({c.url for c in copies} - {h.passage.url}))
            passage = replace(h.passage, tags=merge_tags(copies))
            out.append(Hit(passage, h.score, also_on=others))
        return out
