from pathlib import Path

import pytest

from jobseeker_assistant import snapshots
from jobseeker_assistant.retrieve import Index

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_index() -> Index:
    return Index.from_snapshots(snapshots.load_all(FIXTURES / "sources"))


@pytest.fixture
def sample_html() -> str:
    return (FIXTURES / "sample_page.html").read_text(encoding="utf-8")


@pytest.fixture
def tagged_index() -> Index:
    from jobseeker_assistant.source_tags import load_tags

    d = FIXTURES / "tagged"
    return Index.from_snapshots(snapshots.load_all(d), load_tags(d / "tags.toml"))
