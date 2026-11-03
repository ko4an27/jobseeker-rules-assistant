"""Fetch official pages and store them as clean-text snapshots.

Usage:
    python -m jobseeker_assistant.ingest            # fetch only missing snapshots
    python -m jobseeker_assistant.ingest --refresh  # explicitly re-fetch everything

Fetching is a separate, explicit step (CLAUDE.md rule 6): answering questions never
touches the network for sources, it only reads the saved snapshots.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from . import snapshots
from .snapshots import LINK_MARK, Snapshot

DEFAULT_URL_LIST = snapshots.DEFAULT_SOURCES_DIR / "urls.txt"
USER_AGENT = "jobseeker-rules-assistant/0.1 (snapshot of public pages for a research project)"

# Page furniture that is never part of the rules text.
_DROP_TAGS = ["script", "style", "noscript", "nav", "header", "footer", "aside", "form", "svg"]
_HEADINGS = {"h1": "#", "h2": "##", "h3": "###", "h4": "####"}
_TEXT_TAGS = ["h1", "h2", "h3", "h4", "p", "li", "td", "th", "dt", "dd"]


def read_url_list(path: Path) -> list[str]:
    """Read URLs from a text file, ignoring blank lines and '#' notes."""
    urls = []
    for line in path.read_text(encoding="utf-8").splitlines():
        url = line.split("#", 1)[0].strip()
        if url:
            urls.append(url)
    return urls


def is_link_only(el) -> bool:
    """True if the element is essentially just a link, e.g. 'Read more (kela.fi)'."""
    total = len(el.get_text("", strip=True))
    linked = sum(len(a.get_text("", strip=True)) for a in el.find_all("a"))
    return total > 0 and linked / total >= 0.8


def _content_root(soup: BeautifulSoup):
    """Pick the element that holds the page's real content.

    <main> if present. Otherwise the largest <article>, but only if it holds most of the
    page's text: some sites use <article> for small promo cards, not the main content.
    """
    main = soup.find("main")
    if main:
        return main
    body = soup.body or soup
    articles = soup.find_all("article")
    if articles:
        biggest = max(articles, key=lambda a: len(a.get_text(strip=True)))
        if len(biggest.get_text(strip=True)) >= 0.5 * len(body.get_text(strip=True)):
            return biggest
    return body


def _clean_title(title: str) -> str:
    """'Page - Section - Site name' -> 'Page'."""
    for sep in (" | ", " - "):
        title = title.split(sep, 1)[0]
    return title.strip()


def html_to_text(html: str) -> tuple[str, str]:
    """Extract (title, clean body) from HTML, keeping headings so sections stay citable."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(_DROP_TAGS):
        tag.decompose()
    root = _content_root(soup)

    h1 = root.find("h1")
    if h1:
        title = h1.get_text(" ", strip=True)
    else:
        title = _clean_title(soup.title.get_text(" ", strip=True) if soup.title else "")

    lines: list[str] = []
    for el in root.find_all(_TEXT_TAGS):
        # Skip containers whose text is already captured by a nested text element.
        if el.name in ("li", "td", "dd") and el.find(["p", "li"]):
            continue
        text = " ".join(el.get_text(" ", strip=True).split())
        if not text:
            continue
        if el.name in _HEADINGS:
            lines.append(f"\n{_HEADINGS[el.name]} {text}")
            continue
        if is_link_only(el):
            text = f"{LINK_MARK} {text}"
        lines.append(f"- {text}" if el.name == "li" else text)
    body = "\n".join(lines).strip()
    return title, body


def http_get(url: str) -> str:
    import requests

    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    return resp.text


@dataclass
class IngestReport:
    saved: list[str]
    skipped: list[str]
    failed: dict[str, str]  # url -> reason

    def blocked_hosts(self) -> list[str]:
        return sorted({urlparse(u).netloc for u in self.failed})


def ingest(
    urls: list[str],
    directory: Path | None = None,
    refresh: bool = False,
    fetch: Callable[[str], str] | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> IngestReport:
    directory = directory or snapshots.DEFAULT_SOURCES_DIR
    fetch = fetch or http_get
    report = IngestReport(saved=[], skipped=[], failed={})
    for url in urls:
        target = directory / f"{snapshots.slug_for_url(url)}.md"
        if target.exists() and not refresh:
            report.skipped.append(url)
            continue
        try:
            title, body = html_to_text(fetch(url))
        except Exception as exc:  # network errors, HTTP errors, proxy denials
            report.failed[url] = f"{type(exc).__name__}: {exc}"
            continue
        if len(body) < 200:
            report.failed[url] = "page had almost no text (JS-only page or wrong URL?)"
            continue
        fetched_at = now().replace(microsecond=0).isoformat()
        snapshots.save(Snapshot(url, title, fetched_at, body), directory)
        report.saved.append(url)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="re-fetch existing snapshots")
    parser.add_argument("--urls", type=Path, default=DEFAULT_URL_LIST)
    args = parser.parse_args(argv)

    report = ingest(read_url_list(args.urls), refresh=args.refresh)
    print(f"saved {len(report.saved)}, skipped {len(report.skipped)}, failed {len(report.failed)}")
    for url, reason in report.failed.items():
        print(f"  FAILED {url}\n         {reason}")
    if report.failed:
        print("hosts with failures:", ", ".join(report.blocked_hosts()))
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
