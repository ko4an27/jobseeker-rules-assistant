"""Editorial tags for source pages, kept in `sources/tags.toml`.

Tags are our own reviewed decisions about a page, separate from the fetched snapshot text,
so they survive `make refresh`. A page without an entry gets the defaults below.

    ["https://www.kela.fi/labour-market-subsidy"]
    status = "historical"        # current (default) | historical
    replaced_by = "https://www.kela.fi/unemployment-general-social-security-benefit"
    note = "Abolished 1 May 2026; replaced by the general social security benefit."
    audience = "jobseeker"       # jobseeker (default) | employer
    weight = 1.0                 # retrieval weight; 0 excludes the page
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from . import snapshots

STATUSES = {"current", "historical"}
AUDIENCES = {"jobseeker", "employer"}


@dataclass(frozen=True)
class SourceTags:
    status: str = "current"
    audience: str = "jobseeker"
    weight: float = 1.0
    replaced_by: str = ""
    note: str = ""

    @property
    def historical(self) -> bool:
        return self.status == "historical"


DEFAULT_TAGS = SourceTags()


def parse_tags(data: dict) -> dict[str, SourceTags]:
    tags = {}
    for url, fields in data.items():
        unknown = set(fields) - set(SourceTags.__dataclass_fields__)
        if unknown:
            raise ValueError(f"{url}: unknown tag field(s) {sorted(unknown)}")
        t = SourceTags(**fields)
        if t.status not in STATUSES:
            raise ValueError(f"{url}: status must be one of {sorted(STATUSES)}")
        if t.audience not in AUDIENCES:
            raise ValueError(f"{url}: audience must be one of {sorted(AUDIENCES)}")
        if not 0 <= t.weight <= 1:
            raise ValueError(f"{url}: weight must be between 0 and 1")
        if t.replaced_by and not t.historical:
            raise ValueError(f"{url}: replaced_by only makes sense for historical pages")
        tags[url] = t
    return tags


def load_tags(path: Path | None = None) -> dict[str, SourceTags]:
    path = path or snapshots.DEFAULT_SOURCES_DIR / "tags.toml"
    if not path.exists():
        return {}
    return parse_tags(tomllib.loads(path.read_text(encoding="utf-8")))
