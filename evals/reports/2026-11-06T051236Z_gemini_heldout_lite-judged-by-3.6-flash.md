# Eval report 2026-11-06T05:12:36+0000

LLM: `gemini-3.5-flash-lite` · min_score: `1.0` · min_coverage: `0.5` · commit: `cb13534` · cases: 15

Model calls: 5 (+64 from cache) of max 200 · tokens in/out: 13165/1205 · cost: $0.0000

| Metric | Result |
|---|---|
| passed | 12/15 |
| out_of_scope_refused | 5/5 |
| in_scope_answered | 9/10 |
| source_cited | 9/10 |
| source_retrieved | 10/10 |
| facts_in_answer | 7/10 |
| facts_in_sources | 10/10 |
| retried | 0/15 |
| refused_not_grounded | 0/15 |
| judge_overall | 1/15 |
| judge_correct | 1/1 |
| judge_grounded | 1/1 |
| judge_right_source | 1/1 |
| judge_meaning_preserved | 1/1 |
| judge_plain_language | 1/1 |
| judge_safe_refusal | 1/1 |
| judge_replaced_note | – |
| judge_errors | 14/15 |
| passed · abolished | 1/1 |
| passed · current | 5/8 |
| passed · out_of_scope | 5/5 |
| passed · tricky | 1/1 |

| Case | Category | Pass | Refusal ok | Cited | Retrieved | Facts in answer | Facts in sources | Top score | Coverage |
|---|---|---|---|---|---|---|---|---|---|
| h-gssb-monthly | current | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 18.448 | 0.621 |
| h-status-report | current | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | 22.902 | 1.0 |
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
| h-gssb-monthly | judge error | judge unavailable: gemini returned HTTP 429 for model gemini-3.6-flash: {
  "error": {
    "code": 429,
    "message": "You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To moni |
| h-status-report | judge error | judge unavailable: gemini returned HTTP 429 for model gemini-3.6-flash: {
  "error": {
    "code": 429,
    "message": "You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To moni |
| h-under-25-study | judge error | judge unavailable: gemini returned HTTP 429 for model gemini-3.6-flash: {
  "error": {
    "code": 429,
    "message": "You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To moni |
| h-ps-reduced-ability | judge error | judge unavailable: gemini returned HTTP 429 for model gemini-3.6-flash: {
  "error": {
    "code": 429,
    "message": "You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To moni |
| h-ps-over-60 | judge error | judge unavailable: gemini returned HTTP 429 for model gemini-3.6-flash: {
  "error": {
    "code": 429,
    "message": "You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To moni |
| h-apply-for-jobs | judge error | judge unavailable: gemini returned HTTP 429 for model gemini-3.6-flash: {
  "error": {
    "code": 429,
    "message": "You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To moni |
| h-lmt-travel | judge error | judge unavailable: gemini returned HTTP 429 for model gemini-3.6-flash: {
  "error": {
    "code": 429,
    "message": "You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To moni |
| h-partial-work-ability | judge error | judge unavailable: gemini returned HTTP 429 for model gemini-3.6-flash: {
  "error": {
    "code": 429,
    "message": "You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To moni |
| h-means-test-check | judge error | judge unavailable: gemini returned HTTP 429 for model gemini-3.6-flash: {
  "error": {
    "code": 429,
    "message": "You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To moni |
| h-yleistuki | — |  |
| h-oos-driving-licence | judge error | judge unavailable: gemini returned HTTP 429 for model gemini-3.6-flash: {
  "error": {
    "code": 429,
    "message": "You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To moni |
| h-oos-apartment | judge error | judge unavailable: gemini returned HTTP 429 for model gemini-3.6-flash: {
  "error": {
    "code": 429,
    "message": "You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To moni |
| h-oos-opening-hours | judge error | judge unavailable: gemini returned HTTP 429 for model gemini-3.6-flash: {
  "error": {
    "code": 429,
    "message": "You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To moni |
| h-oos-court-overtime | judge error | judge unavailable: gemini returned HTTP 429 for model gemini-3.6-flash: {
  "error": {
    "code": 429,
    "message": "You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To moni |
| h-oos-appeal-chances | judge error | judge unavailable: gemini returned HTTP 429 for model gemini-3.6-flash: {
  "error": {
    "code": 429,
    "message": "You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To moni |
