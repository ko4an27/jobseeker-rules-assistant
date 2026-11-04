"""Notes for abolished benefits and offices mentioned in the question (sources/abolished.toml).

If someone asks about the labour market subsidy, the answer must say it no longer exists,
whatever passages were retrieved. This is done in code, not left to the model:
- the note is appended to every answer whose question mentions the benefit,
- it cites the passage of a page that states the change (pulled into the sources if needed),
- it is checked against that passage by the grounding check before it is added.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from . import snapshots
from .glossary import _pattern
from .grounding import check_claim
from .retrieve import Hit, Index


@dataclass(frozen=True)
class Abolished:
    name: str
    mentioned_as: tuple[str, ...]
    note: str
    cite: str
    old_page: str = ""


def parse_abolished(data: dict) -> list[Abolished]:
    entries = []
    for raw in data.get("abolished", []):
        unknown = set(raw) - {"name", "mentioned_as", "note", "cite", "old_page"}
        if unknown:
            raise ValueError(f"abolished entry: unknown field(s) {sorted(unknown)}")
        e = Abolished(
            name=raw["name"],
            mentioned_as=tuple(m.lower() for m in raw["mentioned_as"]),
            note=raw["note"],
            cite=raw["cite"],
            old_page=raw.get("old_page", ""),
        )
        if not (e.mentioned_as and e.note and e.cite):
            raise ValueError(f"abolished entry {e.name}: needs mentioned_as, note and cite")
        entries.append(e)
    return entries


def load_abolished(path: Path | None = None) -> list[Abolished]:
    path = path or snapshots.DEFAULT_SOURCES_DIR / "abolished.toml"
    if not path.exists():
        return []
    return parse_abolished(tomllib.loads(path.read_text(encoding="utf-8")))


def mentioned(question: str, entries: list[Abolished]) -> list[Abolished]:
    return [e for e in entries if any(_pattern(m).search(question) for m in e.mentioned_as)]


def add_notes(
    entries: list[Abolished], hits: list[Hit], index: Index, cited: list[int]
) -> tuple[list[Hit], list[str], list[int], set[str]]:
    """Append each entry's note, citing its supporting passage.

    Returns (hits, notes, source numbers to cite, old pages already covered by a note).
    An entry is skipped if its page isn't in the index or the note isn't supported by it.
    """
    hits = list(hits)
    notes, extra, covered = [], [], set()
    for e in entries:
        support = index.best_from_url(e.cite, e.note)
        if support is None:
            continue
        n = next((i for i, h in enumerate(hits, 1) if h.passage.id == support.passage.id), None)
        if n is None:
            hits.append(support)
            n = len(hits)
        labels = [n]
        old = next((i for i in cited if e.old_page and hits[i - 1].passage.url == e.old_page), None)
        if old is not None:
            labels.insert(0, old)
        note = f"Note: {e.note} " + "".join(f"[S{i}]" for i in labels)
        if not check_claim(f"{e.note} [S{n}]", hits).supported:
            continue  # never add a note its own source doesn't back
        notes.append(note)
        extra.extend(labels)
        if e.old_page:
            covered.add(e.old_page)
    return hits, notes, extra, covered
