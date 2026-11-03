"""Snapshot files: one official page saved as clean text, with its URL and fetch date.

File format (Markdown with a small header):

    ---
    url: https://www.kela.fi/...
    title: Page title
    fetched_at: 2026-11-03T17:00:00+00:00
    ---
    # Page title
    ## Section heading
    Paragraph text...
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_SOURCES_DIR = Path(__file__).resolve().parents[2] / "sources"


@dataclass(frozen=True)
class Snapshot:
    url: str
    title: str
    fetched_at: str
    body: str


def slug_for_url(url: str) -> str:
    """Turn a URL into a safe, stable file name, e.g. 'kela.fi__unemployment-benefits'."""
    parsed = urlparse(url)
    host = parsed.netloc.removeprefix("www.")
    path = parsed.path.strip("/") or "index"
    raw = f"{host}__{path}"
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip("-")
    return slug[:150]


def to_text(snap: Snapshot) -> str:
    header = f"---\nurl: {snap.url}\ntitle: {snap.title}\nfetched_at: {snap.fetched_at}\n---\n"
    return header + snap.body.strip() + "\n"


def from_text(text: str) -> Snapshot:
    if not text.startswith("---\n"):
        raise ValueError("snapshot is missing its '---' header")
    header, sep, body = text[4:].partition("\n---\n")
    if not sep:
        raise ValueError("snapshot header is not closed with '---'")
    meta = {}
    for line in header.splitlines():
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    for required in ("url", "fetched_at"):
        if not meta.get(required):
            raise ValueError(f"snapshot header lacks '{required}'")
    return Snapshot(
        url=meta["url"],
        title=meta.get("title", ""),
        fetched_at=meta["fetched_at"],
        body=body.strip(),
    )


def save(snap: Snapshot, directory: Path | None = None) -> Path:
    directory = directory or DEFAULT_SOURCES_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{slug_for_url(snap.url)}.md"
    path.write_text(to_text(snap), encoding="utf-8")
    return path


def load_all(directory: Path | None = None) -> list[Snapshot]:
    directory = directory or DEFAULT_SOURCES_DIR
    return [from_text(p.read_text(encoding="utf-8")) for p in sorted(directory.glob("*.md"))]
