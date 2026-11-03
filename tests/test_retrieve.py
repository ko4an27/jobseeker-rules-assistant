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
