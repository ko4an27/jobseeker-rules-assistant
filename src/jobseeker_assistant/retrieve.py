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
from dataclasses import dataclass

from .snapshots import LINK_MARK, Snapshot
from .source_tags import DEFAULT_TAGS, SourceTags

MAX_PASSAGE_CHARS = 1200
HISTORICAL_WEIGHT = 0.5  # prefer current pages
MAX_LINK_SHARE = 0.6  # sections with more link lines than this are left out of retrieval

_STOPWORDS = set(
    "a an and are as at be by can do does for from how i if in is it my of on or the to "
    "what when where which who will with you your me am this that there".split()
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


def chunk_snapshot(snap: Snapshot, tags: SourceTags = DEFAULT_TAGS) -> list[Passage]:
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
        for part in _split_long("\n".join(lines)):
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

    @classmethod
    def from_snapshots(
        cls, snaps: list[Snapshot], tags: dict[str, SourceTags] | None = None
    ) -> Index:
        tags = tags or {}
        return cls([p for s in snaps for p in chunk_snapshot(s, tags.get(s.url, DEFAULT_TAGS))])

    def best_from_url(self, url: str, query: str) -> Hit | None:
        """Best passage from one page, e.g. to bring in the page that replaced a historical one."""
        hits = [h for h in self.search(query, k=len(self.passages)) if h.passage.url == url]
        if hits:
            return hits[0]
        first = next((p for p in self.passages if p.url == url), None)
        return Hit(first, 0.0) if first else None

    def search(self, query: str, k: int = 4) -> list[Hit]:
        terms = set(tokenize(query))
        hits = []
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
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:k]
