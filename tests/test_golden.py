"""The golden and held-out sets must be valid and grounded in the source snapshots."""

from collections import Counter

import pytest

from jobseeker_assistant import snapshots
from jobseeker_assistant.evals import GOLDEN, HELDOUT, fact_present, load_golden

SETS = {"golden": GOLDEN, "heldout": HELDOUT}


def test_golden_set_shape():
    cases = load_golden(GOLDEN)
    assert len(cases) == 38  # 35 + 3 abolished-benefit cases added on Day 5b
    assert Counter(c.category for c in cases)["out_of_scope"] == 8


def test_heldout_set_shape():
    cases = load_golden(HELDOUT)
    assert len(cases) == 15
    assert sum(c.must_refuse for c in cases) == 5


def test_sets_do_not_share_ids_or_questions():
    golden, heldout = load_golden(GOLDEN), load_golden(HELDOUT)
    assert not {c.id for c in golden} & {c.id for c in heldout}
    assert not {c.question.lower() for c in golden} & {c.question.lower() for c in heldout}


@pytest.mark.parametrize("name", SETS)
def test_out_of_scope_cases_must_refuse(name):
    assert all(c.must_refuse for c in load_golden(SETS[name]) if c.category == "out_of_scope")


@pytest.mark.parametrize("name", SETS)
def test_every_expected_source_has_a_snapshot(name):
    urls = {s.url for s in snapshots.load_all()}
    for case in load_golden(SETS[name]):
        for url in case.expected_sources:
            assert url in urls, f"{case.id}: no snapshot for {url}"


@pytest.mark.parametrize("name", SETS)
def test_every_key_fact_is_in_an_expected_source(name):
    """Guards against expected facts that the sources don't actually say."""
    text = {s.url: s.body for s in snapshots.load_all()}
    for case in load_golden(SETS[name]):
        for fact in case.key_facts:
            assert any(fact_present(fact, text[u]) for u in case.expected_sources), (
                f"{case.id}: '{fact}' not found in any expected source"
            )
