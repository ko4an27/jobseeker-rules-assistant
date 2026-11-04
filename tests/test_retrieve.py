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


def _p(url, text, **tags):
    from jobseeker_assistant.retrieve import Passage
    from jobseeker_assistant.source_tags import SourceTags

    return Passage(f"{url}#0", url, "T", "Work try-out", text, "d", SourceTags(**tags))


CARD = "The maximum duration of a work try-out is six months."


def test_duplicates_keep_one_copy_and_list_the_other_pages():
    from jobseeker_assistant.retrieve import Index

    idx = Index([_p("https://a.test", CARD), _p("https://b.test", CARD), _p("https://c.test", "x")])
    hits = idx.search("work try-out duration")
    cards = [h for h in hits if h.passage.text == CARD]
    assert len(cards) == 1 and len(hits) == 2
    assert {cards[0].passage.url, *cards[0].also_on} == {"https://a.test", "https://b.test"}


def test_duplicates_do_not_fill_top_k():
    from jobseeker_assistant.retrieve import Index

    other = "A work try-out needs approval from the employment authority."
    idx = Index([_p(f"https://{i}.test", CARD) for i in range(4)] + [_p("https://o.test", other)])
    assert len(idx.search("work try-out", k=4)) == 2


def test_duplicate_keeps_best_scoring_copy():
    from jobseeker_assistant.retrieve import Index

    old = _p("https://old.test", CARD, status="historical")
    new = _p("https://new.test", CARD)
    [hit] = Index([old, new]).search("work try-out")
    assert hit.passage.url == "https://new.test"  # historical copy scores half


def test_merge_tags_keeps_employer_warning_and_current_status():
    from jobseeker_assistant.retrieve import merge_tags

    merged = merge_tags(
        [_p("a", CARD, audience="employer"), _p("b", CARD, status="historical", note="n")]
    )
    assert merged.audience == "employer" and not merged.historical
    both_old = merge_tags(
        [_p("a", CARD, status="historical", note="n"), _p("b", CARD, status="historical")]
    )
    assert both_old.historical and both_old.note == "n"


def test_copy_of_employer_text_carries_employer_tag():
    from jobseeker_assistant.retrieve import Index

    emp = _p("https://emp.test", CARD, audience="employer")
    plain = _p("https://plain.test", CARD + " ")  # same text, whitespace differs
    [hit] = Index([plain, emp]).search("work try-out")
    assert hit.passage.tags.audience == "employer"


def test_best_from_url_ignores_dedupe():
    from jobseeker_assistant.retrieve import Index

    idx = Index([_p("https://a.test", CARD), _p("https://b.test", CARD, status="historical")])
    assert idx.best_from_url("https://b.test", "work try-out").passage.url == "https://b.test"


def test_coverage_is_high_when_passage_matches_the_question(fixture_index):
    q = "What is the duration of a work trial?"
    hit = fixture_index.search(q)[0]
    assert fixture_index.coverage(q, hit.passage) == 1.0


def test_coverage_is_low_for_off_topic_words(fixture_index):
    # "benefit" matches, "pizza" and "helsinki" are not in the sources at all.
    q = "benefit pizza helsinki"
    hit = fixture_index.search(q)[0]
    assert fixture_index.coverage(q, hit.passage) < 0.4


def test_coverage_of_empty_question(fixture_index):
    assert fixture_index.coverage("the a of", fixture_index.passages[0]) == 0.0


def test_coverage_ignores_conversational_words(fixture_index):
    # "got", "small", "all" say how someone asks, not what about; they must not count
    # against the question (they used to weigh as much as an off-topic word).
    plain = "part-time work benefit"
    chatty = "i got a small part-time work, do i lose all my benefit??"
    hit = fixture_index.search(plain)[0]
    assert fixture_index.coverage(chatty, hit.passage) == fixture_index.coverage(plain, hit.passage)


def test_coverage_still_penalises_off_topic_words(fixture_index):
    plain = "part-time work benefit"
    hit = fixture_index.search(plain)[0]
    with_off_topic = fixture_index.coverage(plain + " pizza helsinki", hit.passage)
    assert with_off_topic < fixture_index.coverage(plain, hit.passage)


def test_coverage_ignore_list_has_no_topic_words():
    from jobseeker_assistant.retrieve import COVERAGE_IGNORE

    for topic in ("benefit", "work", "pay", "income", "training", "subsidy", "kela", "money"):
        assert topic not in COVERAGE_IGNORE
