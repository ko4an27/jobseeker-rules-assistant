# Eval report 2026-11-04T04:50:21+0000

LLM: `fake` · min_score: `1.0` · min_coverage: `0.5` · commit: `f7761b7` · cases: 35

| Metric | Result |
|---|---|
| passed | 11/35 |
| out_of_scope_refused | 8/8 |
| in_scope_answered | 25/27 |
| source_cited | 22/27 |
| source_retrieved | 27/27 |
| facts_in_answer | 3/27 |
| facts_in_sources | 25/27 |
| passed · abolished | 2/5 |
| passed · current | 1/17 |
| passed · out_of_scope | 8/8 |
| passed · tricky | 0/5 |

| Case | Category | Pass | Refusal ok | Cited | Retrieved | Facts in answer | Facts in sources | Top score | Coverage |
|---|---|---|---|---|---|---|---|---|---|
| gssb-amount | current | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 15.876 | 0.779 |
| gssb-who | current | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | 15.689 | 1.0 |
| gssb-means-test | current | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | 17.433 | 1.0 |
| gssb-waiting-period | current | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | 20.151 | 1.0 |
| gssb-qualifying-period | current | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | 22.674 | 0.667 |
| gssb-start-date | current | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | 21.849 | 0.806 |
| side-part-time | current | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | 18.8 | 1.0 |
| side-short-full-time-job | current | ❌ | ✅ | ❌ | ✅ | ❌ | ✅ | 27.861 | 0.646 |
| side-other-income | current | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | 26.931 | 1.0 |
| wto-duration | current | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | 14.197 | 0.708 |
| wto-benefit | current | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | 17.283 | 1.0 |
| ps-amount | current | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | 12.158 | 0.555 |
| ps-timing | current | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | 12.607 | 0.601 |
| lmt-cost | current | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | 11.872 | 0.871 |
| lmt-apply | current | ❌ | ✅ | ✅ | ✅ | ❌ | ❌ | 11.771 | 1.0 |
| reform-municipalities | current | ❌ | ✅ | ❌ | ✅ | ❌ | ✅ | 8.577 | 0.582 |
| reform-initial-interview | current | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | 20.405 | 0.637 |
| abolished-lms | abolished | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | 12.239 | 1.0 |
| abolished-bua | abolished | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | 9.843 | 0.764 |
| abolished-peruspaivaraha | abolished | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ | 11.406 | 0.483 |
| abolished-tyomarkkinatuki | abolished | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 12.003 | 0.827 |
| abolished-te-office | abolished | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | 7.066 | 0.577 |
| tricky-side-gig | tricky | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ | 28.993 | 0.256 |
| tricky-one-euro | tricky | ❌ | ✅ | ❌ | ✅ | ❌ | ✅ | 15.751 | 0.512 |
| tricky-palkkatuki | tricky | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | 12.158 | 0.687 |
| tricky-tyokokeilu | tricky | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | 14.197 | 0.708 |
| tricky-typo | tricky | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | 14.197 | 1.0 |
| oos-pizza | out_of_scope | ✅ | ✅ | – | – | – | – | 5.034 | 0.229 |
| oos-weather | out_of_scope | ✅ | ✅ | – | – | – | – | 4.457 | 0.188 |
| oos-tax-return | out_of_scope | ✅ | ✅ | – | – | – | – | 7.463 | 0.35 |
| oos-tourist-visa | out_of_scope | ✅ | ✅ | – | – | – | – | 6.408 | 0.371 |
| oos-residence-permit | out_of_scope | ✅ | ✅ | – | – | – | – | 16.424 | 0.45 |
| oos-sue-employer | out_of_scope | ✅ | ✅ | – | – | – | – | 10.362 | 0.372 |
| oos-eviction | out_of_scope | ✅ | ✅ | – | – | – | – | 6.905 | 0.257 |
| oos-appeal-my-case | out_of_scope | ✅ | ✅ | – | – | – | – | 6.282 | 0.169 |
