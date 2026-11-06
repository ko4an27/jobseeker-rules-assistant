# Eval report 2026-11-06T12:06:20+0000

LLM: `gemini-3.5-flash-lite` · min_score: `1.0` · min_coverage: `0.5` · commit: `8cd29e4` · cases: 15

**Note:** the judge (`gemini-3.5-flash-lite`) is the same model that wrote the answers, so judge scores may be lenient. Set JUDGE_MODEL to a different model.

Model calls: 98 (+0 from cache) of max 200 · tokens in/out: 212464/13383 · cost: $0.0000

| Metric | Result |
|---|---|
| passed | 13/15 |
| out_of_scope_refused | 5/5 |
| in_scope_answered | 9/10 |
| source_cited | 9/10 |
| source_retrieved | 10/10 |
| facts_in_answer | 8/10 |
| facts_in_sources | 10/10 |
| retried | 0/15 |
| refused_not_grounded | 0/15 |
| judge_overall | 14/15 |
| judge_correct | 9/9 |
| judge_grounded | 9/9 |
| judge_right_source | 9/9 |
| judge_meaning_preserved | 9/9 |
| judge_plain_language | 15/15 |
| judge_safe_refusal | 12/13 |
| judge_replaced_note | 1/1 |
| judge_errors | 0/15 |
| passed · abolished | 1/1 |
| passed · current | 6/8 |
| passed · out_of_scope | 5/5 |
| passed · tricky | 1/1 |

| Case | Category | Pass | Refusal ok | Cited | Retrieved | Facts in answer | Facts in sources | Top score | Coverage |
|---|---|---|---|---|---|---|---|---|---|
| h-gssb-monthly | current | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 18.448 | 0.621 |
| h-status-report | current | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 22.902 | 1.0 |
| h-under-25-study | current | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | 16.368 | 0.609 |
| h-ps-reduced-ability | current | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 15.327 | 0.864 |
| h-ps-over-60 | current | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 16.351 | 0.68 |
| h-apply-for-jobs | current | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 10.782 | 0.614 |
| h-lmt-travel | current | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 17.574 | 0.752 |
| h-partial-work-ability | current | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ | 11.259 | 0.465 |
| h-means-test-check | abolished | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 19.46 | 0.866 |
| h-yleistuki | tricky | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 13.843 | 1.0 |
| h-oos-driving-licence | out_of_scope | ✅ | ✅ | – | – | – | – | 4.509 | 0.353 |
| h-oos-apartment | out_of_scope | ✅ | ✅ | – | – | – | – | 9.036 | 0.243 |
| h-oos-opening-hours | out_of_scope | ✅ | ✅ | – | – | – | – | 5.826 | 0.423 |
| h-oos-court-overtime | out_of_scope | ✅ | ✅ | – | – | – | – | 11.393 | 0.309 |
| h-oos-appeal-chances | out_of_scope | ✅ | ✅ | – | – | – | – | 8.38 | 0.216 |

## Judge

| Case | Failed criteria | Judge's reasons |
|---|---|---|
| h-gssb-monthly | — |  |
| h-status-report | — |  |
| h-under-25-study | — |  |
| h-ps-reduced-ability | — |  |
| h-ps-over-60 | — |  |
| h-apply-for-jobs | — |  |
| h-lmt-travel | — |  |
| h-partial-work-ability | safe_refusal | safe_refusal: The question is in scope because passage S3 mentions needing a medical certificate for services, but the assistant incorrectly refused to answer. |
| h-means-test-check | — |  |
| h-yleistuki | — |  |
| h-oos-driving-licence | — |  |
| h-oos-apartment | — |  |
| h-oos-opening-hours | — |  |
| h-oos-court-overtime | — |  |
| h-oos-appeal-chances | — |  |
