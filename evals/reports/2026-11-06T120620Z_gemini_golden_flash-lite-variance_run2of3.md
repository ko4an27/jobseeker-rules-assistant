# Eval report 2026-11-06T12:06:20+0000

LLM: `gemini-3.5-flash-lite` · min_score: `1.0` · min_coverage: `0.5` · commit: `8cd29e4` · cases: 38

**Note:** the judge (`gemini-3.5-flash-lite`) is the same model that wrote the answers, so judge scores may be lenient. Set JUDGE_MODEL to a different model.

Model calls: 74 (+0 from cache) of max 200 · tokens in/out: 160500/10212 · cost: $0.0000

| Metric | Result |
|---|---|
| passed | 36/38 |
| out_of_scope_refused | 8/8 |
| in_scope_answered | 30/30 |
| source_cited | 30/30 |
| source_retrieved | 30/30 |
| facts_in_answer | 28/30 |
| facts_in_sources | 29/30 |
| retried | 6/38 |
| refused_not_grounded | 0/38 |
| judge_overall | 37/38 |
| judge_correct | 29/30 |
| judge_grounded | 30/30 |
| judge_right_source | 30/30 |
| judge_meaning_preserved | 30/30 |
| judge_plain_language | 38/38 |
| judge_safe_refusal | 32/32 |
| judge_replaced_note | 8/8 |
| judge_errors | 0/38 |
| passed · abolished | 8/8 |
| passed · current | 15/17 |
| passed · out_of_scope | 8/8 |
| passed · tricky | 5/5 |

| Case | Category | Pass | Refusal ok | Cited | Retrieved | Facts in answer | Facts in sources | Top score | Coverage |
|---|---|---|---|---|---|---|---|---|---|
| gssb-amount | current | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 15.876 | 1.0 |
| gssb-who | current | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 15.689 | 1.0 |
| gssb-means-test | current | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 17.433 | 1.0 |
| gssb-waiting-period | current | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 20.151 | 1.0 |
| gssb-qualifying-period | current | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 22.674 | 0.65 |
| gssb-start-date | current | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 21.849 | 0.806 |
| side-part-time | current | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 18.8 | 1.0 |
| side-short-full-time-job | current | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 27.861 | 0.72 |
| side-other-income | current | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | 26.931 | 1.0 |
| wto-duration | current | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 14.197 | 0.708 |
| wto-benefit | current | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 17.283 | 1.0 |
| ps-amount | current | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 12.158 | 0.742 |
| ps-timing | current | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 12.607 | 0.646 |
| lmt-cost | current | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 11.872 | 0.871 |
| lmt-apply | current | ❌ | ✅ | ✅ | ✅ | ❌ | ❌ | 11.771 | 1.0 |
| reform-municipalities | current | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 8.577 | 0.582 |
| reform-initial-interview | current | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 20.405 | 0.637 |
| abolished-lms | abolished | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 12.239 | 1.0 |
| abolished-bua | abolished | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 9.843 | 1.0 |
| abolished-peruspaivaraha | abolished | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 11.406 | 1.0 |
| abolished-tyomarkkinatuki | abolished | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 12.003 | 1.0 |
| abolished-te-office | abolished | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 7.066 | 0.696 |
| abolished-lms-current-pages | abolished | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 13.747 | 1.0 |
| abolished-bua-per-day | abolished | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 12.703 | 1.0 |
| abolished-te-office-nearest | abolished | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 5.399 | 0.589 |
| tricky-side-gig | tricky | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 28.993 | 0.828 |
| tricky-one-euro | tricky | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 15.751 | 1.0 |
| tricky-palkkatuki | tricky | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 12.158 | 1.0 |
| tricky-tyokokeilu | tricky | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 14.197 | 0.708 |
| tricky-typo | tricky | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 14.197 | 1.0 |
| oos-pizza | out_of_scope | ✅ | ✅ | – | – | – | – | 5.034 | 0.229 |
| oos-weather | out_of_scope | ✅ | ✅ | – | – | – | – | 4.457 | 0.188 |
| oos-tax-return | out_of_scope | ✅ | ✅ | – | – | – | – | 7.463 | 0.35 |
| oos-tourist-visa | out_of_scope | ✅ | ✅ | – | – | – | – | 6.408 | 0.371 |
| oos-residence-permit | out_of_scope | ✅ | ✅ | – | – | – | – | 16.424 | 0.45 |
| oos-sue-employer | out_of_scope | ✅ | ✅ | – | – | – | – | 10.362 | 0.372 |
| oos-eviction | out_of_scope | ✅ | ✅ | – | – | – | – | 6.905 | 0.264 |
| oos-appeal-my-case | out_of_scope | ✅ | ✅ | – | – | – | – | 6.282 | 0.169 |

## Judge

| Case | Failed criteria | Judge's reasons |
|---|---|---|
| gssb-amount | — |  |
| gssb-who | — |  |
| gssb-means-test | — |  |
| gssb-waiting-period | — |  |
| gssb-qualifying-period | — |  |
| gssb-start-date | — |  |
| side-part-time | — |  |
| side-short-full-time-job | — |  |
| side-other-income | — |  |
| wto-duration | — |  |
| wto-benefit | — |  |
| ps-amount | — |  |
| ps-timing | — |  |
| lmt-cost | — |  |
| lmt-apply | correct | correct: The answer misses the expected key fact that labour market training is applied for via the e-service. |
| reform-municipalities | — |  |
| reform-initial-interview | — |  |
| abolished-lms | — |  |
| abolished-bua | — |  |
| abolished-peruspaivaraha | — |  |
| abolished-tyomarkkinatuki | — |  |
| abolished-te-office | — |  |
| abolished-lms-current-pages | — |  |
| abolished-bua-per-day | — |  |
| abolished-te-office-nearest | — |  |
| tricky-side-gig | — |  |
| tricky-one-euro | — |  |
| tricky-palkkatuki | — |  |
| tricky-tyokokeilu | — |  |
| tricky-typo | — |  |
| oos-pizza | — |  |
| oos-weather | — |  |
| oos-tax-return | — |  |
| oos-tourist-visa | — |  |
| oos-residence-permit | — |  |
| oos-sue-employer | — |  |
| oos-eviction | — |  |
| oos-appeal-my-case | — |  |
