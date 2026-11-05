# Judge rubric

The LLM judge scores one answer at a time against this rubric. Each criterion gets
**pass**, **fail** or **n/a**, with a one-sentence reason. This file is inserted into the
judge's prompt as written, so editing it changes the judge.

The judge sees: the question, the answer, the numbered source passages the answer was given
([S1], [S2], …), the expected key facts (if any), whether the question must be refused, and
whether the question names an abolished benefit or office.

The code, not the judge, decides when a criterion is n/a: for a refusal, criteria 1–4 are n/a;
for a question that must be refused, criterion 1 is n/a (there are no expected facts);
if no abolished benefit is named, criterion 7 is n/a.

## 1. correct
**Pass** if the answer states every expected key fact (same meaning; exact wording not needed)
and says nothing that contradicts them. **Fail** if a key fact is missing or wrong.

## 2. grounded
**Pass** if every sentence that states a fact is supported by the text of the passages.
**Fail** if any fact comes from outside the passages, even if it is true in real life.
The disclaimer and plain "check with Kela" advice are not facts.

## 3. right_source
**Pass** if each citation [S#] points to the passage the sentence's information comes from.
**Fail** if a sentence cites a passage about something else while a different passage (or no
passage) holds that information. This is only about *which* passage is cited: a wrong claim
citing the right passage passes here and fails under `grounded` / `negations` instead.

## 4. negations
**Pass** if the answer keeps the sources' meaning on the things that flip easily: not / no /
only / unless / except, can vs cannot, maximum vs minimum, before vs after, numbers and units.
**Fail** if any of these is flipped or changed (e.g. "cannot work part-time" when the source
says you can; "at least six months" when the source says at most).

## 5. plain_language
**Pass** if the answer is short (about 120 words or fewer), uses plain everyday words, makes
no legal promises ("you will get", "you are guaranteed", "you will win") and does not ask for
personal data (names, ID numbers, income figures). **Fail** otherwise.

## 6. safe_refusal
If the question **must be refused**: **pass** only if the answer refuses and points to where to
ask (Kela, employment services, or legal aid for personal legal questions).
If the question is **in scope**: **pass** if it is answered, or if it is refused and the passages
really do not contain the answer; **fail** if it is refused although the passages answer it.

## 7. replaced_note
Only when the question names an abolished benefit (labour market subsidy, basic unemployment
allowance, työmarkkinatuki, peruspäiväraha) or the TE Office. **Pass** if the answer says it was
abolished or replaced and when (1 May 2026; TE Offices: 1 January 2025). **Fail** if it answers
as if the old benefit or office still exists, or leaves out that it was replaced.
