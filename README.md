# EU AI Act RAG Assistant

A question-answering assistant for the **EU AI Act** ([Regulation (EU) 2024/1689](https://eur-lex.europa.eu/eli/reg/2024/1689/oj)).
Ask in English or Turkish; the assistant answers **only from the text of the regulation**, cites the
passages it used, links to the exact page of the official PDF, and says
*"I could not find an answer to this in the EU AI Act."* instead of guessing.

The project is built around one question: **can a user check the answer?** Every answer comes with the
passages the model read and a link to the official document, and the whole system is measured against a
fixed evaluation set.

<!-- Add a screenshot of the web UI here: docs/screenshot.png -->

## How it works

```
Indexing (once)   PDF -> clean headers/footers -> chunk -> label section -> embed -> ChromaDB
Query (per ask)   question -> embed -> retrieve 5 chunks -> LLM answers from chunks only -> answer + sources
```

| Step | File | What it does |
|---|---|---|
| Ingest | `ingest.py` | Reads the 144-page PDF, removes running headers/footers, splits it into 768 overlapping chunks (~1000 characters, 200 overlap, cut at word boundaries) and labels each chunk as `recital`, `article` or `annex`. |
| Index | `index.py` | Embeds chunks with `intfloat/multilingual-e5-base` (768 dimensions, runs locally) and stores them in a persistent ChromaDB collection. |
| Retrieve | `search.py` | Finds the nearest chunks to a question. Three strategies: `baseline`, `body_only`, `mixed` (default). |
| Answer | `rag.py` | Drops chunks with distance > 0.45, numbers the rest and asks the LLM (`openai/gpt-oss-120b` on Groq, `temperature=0`) to answer only from them and cite `[n]`. If nothing is close enough, the LLM is not called. |
| Serve | `app.py`, `static/index.html` | FastAPI service (`POST /ask`, `GET /health`, `/docs`) and a small web UI that shows each source passage and opens the official PDF at the cited page. |
| Evaluate | `evaluate.py`, `eval/questions.json` | Runs a 20-question evaluation set and reports retrieval and answer metrics. |

Design choices worth noting:
- **Two safeguards against made-up answers:** a distance threshold (off-topic questions never reach the LLM) and a prompt rule to refuse when the passages do not contain the answer.
- **Verifiability:** the UI shows the exact passage the model read and links to `ai_act.pdf#page=N`.
- **Model output is treated as untrusted:** the UI renders it with `textContent`, never `innerHTML` (prevents XSS).
- **Provider-agnostic:** the LLM is called through the OpenAI-compatible API, so Groq and a local Ollama model are interchangeable via `.env`.

## Evaluation

`eval/questions.json` contains 20 questions: 17 in scope (3 in Turkish), 1 off-topic and 2 traps that look
related but whose answer is not in the regulation (a GDPR fine, the President of the European Commission).
Each in-scope question lists the article or annex that contains the answer; three questions with a precise
answer also list facts the answer must contain (e.g. `EUR 35 000 000` and `7 %` for the fine in Article 99(3)).

Metrics:
- **Hit@5:** a chunk from the expected article/annex is among the 5 retrieved chunks.
- **Binding-text share:** share of retrieved chunks that come from articles or annexes rather than recitals.
- **Answer/refusal decision:** the system answers in-scope questions and refuses the others.
- **Fact check:** for the 3 questions with required facts, whether the answer is `correct`, `refused` or `wrong`.
- **Out-of-scope answered:** off-topic or trap questions that got an answer (should be 0).

### Results

| Strategy | Hit@5 | Binding-text share | Answer/refusal decision | Fact check (correct / refused / wrong) | Out-of-scope answered |
|---|---|---|---|---|---|
| `baseline`: 5 nearest chunks | 11/17 | 34% | 19/20 | 1 / 1 / **1** | 0 |
| `body_only`: articles and annexes only | 16/17 | 100% | 16/20 | 0 / 3 / 0 | 0 |
| `mixed` (default): 4 article/annex chunks + 1 recital | 16/17 | 80% | 18/20 and 19/20 (two runs) | 1 / 2 / 0 and 1 / 1 / **1** (two runs) | 0 |

What the numbers say:
- **Retrieval was the bottleneck, not the model.** In the baseline, recitals (the explanatory preamble) are 41% of all chunks but 66% of retrieved chunks, crowding out the binding articles. Restricting or rebalancing retrieval raised Hit@5 from 11/17 to 16/17.
- **Dropping recitals entirely hurts.** `body_only` refuses questions it should answer. Recitals often use the same words as the question, while articles use legal cross-references: Article 113 sets the start date of the prohibitions as *"Chapters I and II shall apply from 2 February 2025"*, whereas recital 179 says *"the prohibitions ... should already apply from 2 February 2025"*. `mixed` keeps one recital as a bridge and answers more.
- **"Answer/refusal decision" alone is misleading.** It counts a confident wrong answer as a success and a safe refusal as a failure. The fact check was added for this reason.
- **One error is still open.** For the maximum fine for prohibited practices, the system sometimes answers with the general-purpose AI model fine (3% or EUR 15M, Article 101) instead of the correct one (7% or EUR 35M, Article 99(3)). See [FINDINGS.md](FINDINGS.md).

Results per question are saved in `eval/results/`. Notes on the measurement:
- The `body_only` fact-check numbers were computed from its saved answers after the check was added.
- Groq output is not fully deterministic even at `temperature=0`; the same strategy gave different answers to one question in two runs.
- 20 questions are enough to find problems and compare strategies, not to make statistically precise claims.

## Setup

Requirements: Python 3.11 and a free [Groq](https://console.groq.com) API key (or a local [Ollama](https://ollama.com) model).

```bash
conda create -n rag python=3.11 -y
conda activate rag
pip install -r requirements.txt
```

Create `.env` from the example and add your key:

```bash
copy .env.example .env      # Windows (use cp on macOS/Linux)
```

The official PDF is included as `data/ai_act.pdf`. Build the index (downloads the embedding model, about 1 GB, on first run):

```bash
python index.py
```

## Usage

```bash
# Web UI and API: open http://127.0.0.1:8000 (API docs at /docs)
uvicorn app:app --reload

# Command line
python rag.py "When do the prohibitions on AI practices start to apply?"
python search.py --strategy mixed "What is an AI regulatory sandbox?"   # retrieval only, no LLM

# Evaluation (retrieval only: fast, no API calls)
python evaluate.py --strategy mixed
# Evaluation including generated answers (about 5 minutes on Groq's free tier)
python evaluate.py --strategy mixed --llm --label mixed_llm
```

API example:

```bash
curl -X POST http://127.0.0.1:8000/ask -H "Content-Type: application/json" \
     -d "{\"question\": \"Which AI practices are prohibited?\"}"
```

## Project structure

```
data/ai_act.pdf          source document
eval/questions.json      evaluation set with expected articles and required facts
eval/results/            CSV output of each evaluation run
static/index.html        web UI
ingest.py index.py search.py rag.py app.py evaluate.py
FINDINGS.md              problems found during evaluation
```

## Limitations and next steps

- Retrieval finds the right article but not always the right paragraph (Article 99 has several fine levels). Next: prepend the article number and title to each chunk before embedding (contextual chunk headers) and re-measure the open fine error.
- The fact check covers only 3 questions; most answers are still judged by retrieval metrics and by reading them.
- Answers are generated in the question's language from English text; Turkish answers may shift legal meaning in translation.
- Compare models (`gpt-oss-120b`, `gpt-oss-20b`, a local Ollama model) on the same evaluation set.

This is a learning project, not legal advice. Always check the cited pages.
