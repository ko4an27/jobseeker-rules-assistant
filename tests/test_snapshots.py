import pytest

from jobseeker_assistant import snapshots
from jobseeker_assistant.snapshots import Snapshot


def test_slug_is_filesystem_safe_and_stable():
    slug = snapshots.slug_for_url("https://www.kela.fi/unemployment-benefits?x=1")
    assert slug == "kela.fi__unemployment-benefits"
    assert "/" not in snapshots.slug_for_url("https://tyomarkkinatori.fi/en/a/b/c")


def test_roundtrip_save_and_load(tmp_path):
    snap = Snapshot("https://example.test/a", "Title", "2026-11-03T00:00:00+00:00", "# T\nBody")
    snapshots.save(snap, tmp_path)
    assert snapshots.load_all(tmp_path) == [snap]


def test_from_text_rejects_missing_header():
    with pytest.raises(ValueError):
        snapshots.from_text("no header here")


def test_from_text_requires_url_and_date():
    with pytest.raises(ValueError, match="fetched_at"):
        snapshots.from_text("---\nurl: https://x.test\n---\nbody")
