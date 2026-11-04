import pytest

from jobseeker_assistant import snapshots
from jobseeker_assistant.source_tags import DEFAULT_TAGS, load_tags, parse_tags


def test_defaults_for_untagged_pages():
    assert DEFAULT_TAGS.status == "current" and DEFAULT_TAGS.audience == "jobseeker"
    assert DEFAULT_TAGS.weight == 1.0 and not DEFAULT_TAGS.historical


def test_parse_tags_reads_fields():
    tags = parse_tags({"https://a.test": {"status": "historical", "replaced_by": "https://b.test"}})
    assert tags["https://a.test"].historical
    assert tags["https://a.test"].replaced_by == "https://b.test"


@pytest.mark.parametrize(
    "fields",
    [
        {"status": "old"},
        {"audience": "everyone"},
        {"weight": 2},
        {"colour": "red"},
        {"replaced_by": "https://b.test"},  # replaced_by on a current page
    ],
)
def test_parse_tags_rejects_bad_values(fields):
    with pytest.raises(ValueError):
        parse_tags({"https://a.test": fields})


def test_missing_tags_file_means_no_tags(tmp_path):
    assert load_tags(tmp_path / "nope.toml") == {}


def test_real_tags_file_is_valid_and_points_at_real_snapshots():
    """Every tagged URL, and every replaced_by URL, must have a snapshot."""
    tags = load_tags()
    urls = {s.url for s in snapshots.load_all()}
    assert tags, "sources/tags.toml should not be empty"
    for url, t in tags.items():
        assert url in urls, f"tagged URL has no snapshot: {url}"
        if t.replaced_by:
            assert t.replaced_by in urls, f"replacement has no snapshot: {t.replaced_by}"
