import pytest

from jobseeker_assistant import snapshots
from jobseeker_assistant.answer import answer_question
from jobseeker_assistant.glossary import Term, expand, load_glossary, parse_glossary
from jobseeker_assistant.llm import FakeLLM

PAY = Term(("palkkatuki",), ("pay subsidy",), "reviewed", why="Finnish name")
GIG = Term(("side gig", "gig"), ("part-time work", "earned income"), "reviewed", why="slang")


def test_expand_adds_page_wording_for_retrieval_and_replaces_for_coverage():
    exp = expand("palkkatuki - how much does it cover?", [PAY])
    assert exp.retrieval_query == "palkkatuki - how much does it cover? pay subsidy"
    assert exp.coverage_query == "pay subsidy - how much does it cover?"
    assert exp.used == (PAY,)


def test_expand_matches_whole_words_and_longest_phrase():
    assert expand("Gigantic question", [GIG]).used == ()
    exp = expand("i got a small side gig", [GIG])
    assert exp.coverage_query == "i got a small part-time work"
    assert exp.retrieval_query.endswith("part-time work earned income")


def test_expand_is_case_insensitive_and_no_op_without_terms():
    assert expand("PALKKATUKI?", [PAY]).used == (PAY,)
    plain = expand("How long is a work try-out?", [])
    assert plain.retrieval_query == plain.coverage_query == plain.question


@pytest.mark.parametrize(
    "raw, msg",
    [
        ({"match": ["x"], "means": ["y"], "origin": "guess"}, "origin"),
        ({"match": ["x"], "means": ["y"], "origin": "source"}, "source"),
        ({"match": ["x"], "means": ["y"], "origin": "reviewed"}, "why"),
        ({"match": [], "means": ["y"], "origin": "reviewed", "why": "w"}, "match"),
        ({"match": ["x"], "means": ["y"], "origin": "reviewed", "why": "w", "z": 1}, "unknown"),
    ],
)
def test_parse_glossary_rejects_bad_entries(raw, msg):
    with pytest.raises(ValueError, match=msg):
        parse_glossary({"term": [raw]})


def test_real_glossary_loads_and_has_both_origins():
    terms = load_glossary()
    assert {t.origin for t in terms} == {"source", "reviewed"}
    assert any("palkkatuki" in t.match for t in terms)


def test_source_entries_are_really_paired_on_their_page():
    """origin=source means the page says '<English term> (<Finnish term>'."""
    bodies = {s.url: " ".join(s.body.lower().split()) for s in snapshots.load_all()}
    for t in load_glossary():
        if t.origin != "source":
            continue
        assert t.source in bodies, f"{t.match[0]}: no snapshot for {t.source}"
        assert f"{t.means[0].lower()} ({t.match[0]}" in bodies[t.source], (
            f"{t.match[0]}: page doesn't pair it with '{t.means[0]}'"
        )


def test_reviewed_entries_are_not_claimed_by_pages():
    """A 'reviewed' Finnish service name should really be absent from the English pages;
    if a page starts using it, the entry should become origin=source."""
    text = " ".join(s.body.lower() for s in snapshots.load_all())
    for name in ("palkkatuki", "työkokeilu", "työvoimakoulutus"):
        assert name not in text


def test_answer_uses_glossary_and_reports_it(fixture_index):
    trial = Term(("työkokeilu",), ("work trial duration",), "reviewed", why="Finnish name")
    q = "työkokeilu?"
    assert answer_question(q, fixture_index, FakeLLM()).refused
    ans = answer_question(q, fixture_index, FakeLLM(), glossary=[trial])
    assert not ans.refused and ans.glossary_used == ["työkokeilu"]
    assert "example.test/work-trial" in ans.citations[0].url


def test_glossary_never_rewrites_terms_the_pages_already_use():
    """Replacing page wording with other words can only lower coverage (it happened once:
    'TE office' -> 'TE Services'). Reviewed match phrases must not be page wording,
    except these, each checked by hand:"""
    from jobseeker_assistant.glossary import _pattern

    known = {
        "moved": "appears once; the pages say 'transferred' for the 2025 reform",
        "te-palvelut": "appears only inside the link 'te-palvelut.fi'",
    }
    text = " ".join(s.body for s in snapshots.load_all())
    for t in load_glossary():
        if t.origin != "reviewed":
            continue
        for m in t.match:
            if _pattern(m).search(text):
                assert m in known, f"'{m}' already appears on the pages; don't rewrite it"
