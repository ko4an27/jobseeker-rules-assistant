from jobseeker_assistant.grounding import check_answer, check_claim, split_claims, stem
from jobseeker_assistant.retrieve import Hit, Passage

WORK_TRIAL = Passage(
    "u#0",
    "https://example.test/work-trial",
    "Work trial",
    "Duration",
    "A work trial lasts at most six months. The employment office must approve it.",
    "d",
)
SIDE = Passage(
    "s#0",
    "https://example.test/side-income",
    "Side income",
    "Part-time work",
    "Each euro you earn reduces the benefit by 50 cents.",
    "d",
)
HITS = [Hit(WORK_TRIAL, 5.0), Hit(SIDE, 4.0)]


def test_split_claims_keeps_citations_and_decimals():
    assert split_claims("It is EUR 37.21 a day. [S1] Yes! Check [S2]") == [
        "It is EUR 37.21 a day.[S1]",
        "Yes!",
        "Check [S2]",
    ]


def test_stem():
    assert stem("lasts") == stem("last") == "last"
    assert stem("approved") == "approv"


def test_supported_claims_pass():
    result = check_answer(
        "A work trial lasts at most six months [S1]. "
        "Each euro you earn reduces the benefit by 50 cents [S2].",
        HITS,
    )
    assert result.ok and len(result.checks) == 2


def test_number_not_in_cited_source_fails():
    c = check_claim("Each euro you earn reduces the benefit by 60 cents [S2].", HITS)
    assert not c.supported and c.reason == "number 60 not in source"


def test_number_from_the_wrong_source_fails():
    # 50 is in S2, not in the cited S1.
    assert not check_claim("A work trial lasts 50 days [S1].", HITS).supported


def test_claim_about_something_else_fails():
    c = check_claim("You must pay income tax on holiday pay abroad [S1].", HITS)
    assert not c.supported and "key words" in c.reason


def test_missing_and_invented_citations_fail():
    assert check_claim("The work trial lasts six months.", HITS).reason == "no citation"
    assert check_claim("It lasts six months [S7].", HITS).reason == "invented citation [S7]"


def test_short_connective_sentence_is_not_a_claim():
    result = check_answer("Yes. A work trial lasts at most six months [S1].", HITS)
    assert result.ok


def test_answer_without_any_cited_claim_fails():
    result = check_answer("Yes.", HITS)
    assert not result.ok and result.unsupported[0].reason == "no cited claim in the answer"
