# Findings

Problems found while testing the assistant, in the order they were found. Each entry says what happened,
why, and its status. Question numbers (q1 to q20) refer to `eval/questions.json`.

## 1. Answers were incomplete (baseline)
- **Observed:** Article 5 lists eight prohibited practices. Asked "Which AI practices are prohibited?", the answer covered about half of them and repeated some.
- **Cause:** Article 5 is long and split over several chunks; only two of them reached the top 5. The rest were recitals.
- **Status:** Retrieval improved (see 3). The answer is still limited by how many chunks fit in the context.

## 2. Answers cited recitals instead of binding articles (baseline)
- **Observed:** q2 ("When do the prohibitions start to apply?") was answered correctly (2 February 2025) but from recital 179, not from Article 113.
- **Why it matters:** recitals explain the law; articles are the law. Exceptions and exact conditions are in the articles.
- **Status:** Partly addressed by labeling chunks (see 3).

## 3. Retrieval over-selects recitals
- **Observed:** recitals are 41% of all chunks (314 of 768) but 66% of the chunks retrieved by the baseline. Baseline Hit@5 was 11/17.
- **Likely cause:** recitals are written in plain language and look more like a question than the legal wording of articles do.
- **Change:** each chunk is labeled `recital`, `article` or `annex` (the boundaries are "HAVE ADOPTED THIS REGULATION" and the first "ANNEX I" heading). Two strategies were compared with the baseline:
  - `body_only` (articles and annexes only): Hit@5 16/17.
  - `mixed` (4 article/annex chunks + 1 recital): Hit@5 16/17.
- **Status:** `mixed` is the default (see 6).

## 4. A confident wrong answer passed every automatic check (q17)
- **Observed:** q17 asks in Turkish for the maximum fine for prohibited AI practices. The correct answer is Article 99(3): up to EUR 35 000 000 or 7% of worldwide annual turnover. The system answered "3% or EUR 15 000 000" and cited a valid passage, which was Article 101(1): the fine for **providers of general-purpose AI models**.
- **Why it matters:** the answer was fluent, cited a real passage, and passed both the answer/refusal check and the citation check. It was only found by reading it.
- **Language dependence:** the same question in English (q3) was refused instead.
- **Status:** **open.** The `must_contain` fact check now catches it automatically. With `mixed`, q17 was refused in one run and wrong again in another (see 8).

## 5. The right article is retrieved, but not the right paragraph (q3)
- **Observed:** with `mixed`, q3 counts as a Hit@5 because a chunk from Article 99 is retrieved. That chunk contains paragraphs 5 to 7 (EUR 7 500 000 or 1% for supplying incorrect information, rules for SMEs). Paragraph 3 with the EUR 35M / 7% fine was not retrieved, so the model correctly refused.
- **Cause:** the query says "prohibited AI practices", which pulls in Article 5. The chunk with paragraph 3 does not contain the article title "Penalties", which ended up in an earlier chunk.
- **Next:** prepend the article number and title to every chunk before embedding (contextual chunk headers).
- **Measurement lesson:** Hit@5 checks the article, not the paragraph that holds the answer.

## 6. Recitals bridge the question's wording and the legal wording
- **Observed:** `body_only` refused q2, q3, q8 and q17. `mixed` answered q2 and q8.
- **Cause (q2):** Article 113 sets the date as "Chapters I and II shall apply from 2 February 2025". It never says "prohibitions". Recital 179 says "the prohibitions ... should already apply from 2 February 2025", which matches the question. q8 (chatbot transparency) follows the same pattern.
- **Decision:** `mixed` keeps one recital per answer. It answers more questions than `body_only` while answering none of the off-topic or trap questions.

## 7. Bug in the evaluation itself: invisible characters
- **Observed:** the first fact-check run marked the correct q2 answer as wrong.
- **Cause:** the model wrote "2 February 2025" with a narrow no-break space (U+202F) after "2", and the pattern expected a normal space.
- **Fix:** answers are whitespace-normalized before matching. Saved results were re-scored from the stored answers.
- **Lesson:** an evaluation script is code too and needs testing.

## 8. Same settings, different answers
- **Observed:** two runs of `mixed` with `temperature=0` gave different answers to q17 (refused once, wrong once) and different answer/refusal scores (18/20 and 19/20).
- **Implication:** single-run differences of one question are not meaningful. Comparisons should use several runs or look at specific questions.

## 9. Possible translation shift (not yet verified)
- **Observed:** one Turkish answer about the biometric categorisation ban may have rendered "sex life or sexual orientation" as "cinsiyet" (sex/gender), which changes the legal meaning.
- **Status:** to be verified against the passage.

## 10. Sources were shown for refusals (fixed)
- **Observed:** when the answer was "I could not find an answer", the sources were still listed, suggesting they were used.
- **Fix:** sources are shown only when an answer was found (command line and API).

## Measurement notes
- The baseline metrics were first computed per page. Page 44 contains both recitals and articles, and Articles 4 and 5 both start on page 51, so some results were ambiguous. The evaluation now uses chunk labels.
- 20 questions are enough to find problems and compare strategies, not to make statistically precise claims.
