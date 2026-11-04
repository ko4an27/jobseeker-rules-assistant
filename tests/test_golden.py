"""The golden set itself must be valid and grounded in the source snapshots."""

from collections import Counter

from jobseeker_assistant import snapshots
from jobseeker_assistant.evals import fact_present, load_golden


def test_golden_set_shape():
    cases = load_golden()
    counts = Counter(c.category for c in cases)
    assert len(cases) == 35
    assert counts["out_of_scope"] == 8
    assert all(c.must_refuse for c in cases if c.category == "out_of_scope")


def test_every_expected_source_has_a_snapshot():
    urls = {s.url for s in snapshots.load_all()}
    for case in load_golden():
        for url in case.expected_sources:
            assert url in urls, f"{case.id}: no snapshot for {url}"


def test_every_key_fact_is_in_an_expected_source():
    """Guards against golden facts that the sources don't actually say."""
    text = {s.url: s.body for s in snapshots.load_all()}
    for case in load_golden():
        for fact in case.key_facts:
            assert any(fact_present(fact, text[u]) for u in case.expected_sources), (
                f"{case.id}: '{fact}' not found in any expected source"
            )
