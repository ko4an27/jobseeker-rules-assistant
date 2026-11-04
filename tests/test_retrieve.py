from jobseeker_assistant.retrieve import Index, chunk_snapshot, tokenize
from jobseeker_assistant.snapshots import Snapshot


def test_tokenize_lowercases_and_drops_stopwords():
    assert tokenize("Can I do a Work Trial?") == ["work", "trial"]
    assert tokenize("työkokeilu Kelan") == ["työkokeilu", "kelan"]


def test_chunk_snapshot_splits_by_section():
    snap = Snapshot("https://x.test", "Page", "d", "# Page\nIntro\n## A\nText a\n## B\nText b")
    passages = chunk_snapshot(snap)
    assert [p.section for p in passages] == ["Page", "A", "B"]
    assert passages[1].text == "Text a" and passages[1].url == "https://x.test"


def test_chunk_snapshot_splits_very_long_sections():
    body = "## Long\n" + "\n".join(["word " * 60] * 10)
    passages = chunk_snapshot(Snapshot("https://x.test", "P", "d", body))
    assert len(passages) > 1
    assert all(len(p.text) <= 1200 for p in passages)
    assert len({p.id for p in passages}) == len(passages)


def test_search_ranks_relevant_section_first(fixture_index):
    top = fixture_index.search("how long can a work trial last", k=2)[0]
    assert top.passage.url == "https://example.test/work-trial"
    assert top.passage.section == "Duration"


def test_search_finds_side_income_rule(fixture_index):
    top = fixture_index.search("part-time job earn euro benefit")[0]
    assert top.passage.section == "Part-time work"


def test_search_returns_nothing_for_unrelated_question(fixture_index):
    assert fixture_index.search("best pizza helsinki") == []


def test_empty_index_is_safe():
    assert Index([]).search("anything") == []


def test_link_share_counts_link_lines():
    from jobseeker_assistant.retrieve import Passage

    p = Passage("id", "u", "t", "s", "Text\n- [link] A\n- [link] B\n- real item", "d")
    assert p.link_share == 0.5


def test_link_list_sections_are_not_retrieved(tagged_index):
    hits = tagged_index.search("unemployed jobseeker contact details forms", k=10)
    assert hits and all(h.passage.section != "Read more" for h in hits)


def test_historical_pages_rank_below_current(tagged_index):
    hits = tagged_index.search("unemployed jobseeker earnings-related allowance", k=2)
    assert hits[0].passage.url == "https://example.test/new-benefit"


def test_passage_weight_rules():
    from jobseeker_assistant.retrieve import HISTORICAL_WEIGHT, Passage, passage_weight
    from jobseeker_assistant.source_tags import SourceTags

    plain = Passage("id", "u", "t", "s", "rule text", "d")
    assert passage_weight(plain) == 1.0
    old = Passage("id", "u", "t", "s", "rule text", "d", SourceTags(status="historical"))
    assert passage_weight(old) == HISTORICAL_WEIGHT
    off = Passage("id", "u", "t", "s", "rule text", "d", SourceTags(weight=0))
    assert passage_weight(off) == 0
    links = Passage("id", "u", "t", "s", "- [link] a\n- [link] b\n- [link] c\nx", "d")
    assert passage_weight(links) == 0


def test_best_from_url(tagged_index):
    hit = tagged_index.best_from_url("https://example.test/new-benefit", "who can get it")
    assert hit.passage.url == "https://example.test/new-benefit"
    assert tagged_index.best_from_url("https://example.test/none", "q") is None
