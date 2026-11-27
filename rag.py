"""Step 3: Retrieve relevant chunks and ask an LLM to answer using only those chunks."""
import os
import sys

from dotenv import load_dotenv
from openai import OpenAI

from search import search

load_dotenv()
client = OpenAI(
    base_url=os.environ["LLM_BASE_URL"],
    api_key=os.environ["LLM_API_KEY"],
    max_retries=10,  # free tier has a tokens-per-minute limit; back off and retry on 429
)

MODEL = os.environ["LLM_MODEL"]
TOP_K = 5
MAX_DISTANCE = 0.45  # chunks farther than this are treated as irrelevant
NOT_FOUND = "I could not find an answer to this in the EU AI Act."

SYSTEM_PROMPT = f"""You answer questions about the EU AI Act (Regulation (EU) 2024/1689).

Rules:
- Use ONLY the numbered context passages. Do not use outside knowledge.
- After each claim, cite the passage number(s) in square brackets, e.g. [2].
- If the passages do not contain the answer, reply exactly: "{NOT_FOUND}"
- Answer in the same language as the question.
- Be concise: at most 5 sentences."""


def build_context(hits):
    """Number each passage so the model can cite it."""
    return "\n\n".join(
        f"[{i}] (page {meta['page']})\n{doc}"
        for i, (doc, meta, _) in enumerate(hits, start=1)
    )


def answer(question):
    hits = [h for h in search(question, k=TOP_K) if h[2] <= MAX_DISTANCE]
    if not hits:
        return NOT_FOUND, []  # nothing relevant: skip the LLM call entirely

    response = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Context:\n{build_context(hits)}\n\nQuestion: {question}"},
        ],
    )
    return response.choices[0].message.content, hits


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "Which AI practices are prohibited?"
    text, hits = answer(question)
    print(f"Question: {question}\n\nAnswer:\n{text}")
    if text.strip() != NOT_FOUND:
        print("\nSources:")
        for i, (_, meta, dist) in enumerate(hits, start=1):
            print(f"  [{i}] page {meta['page']} (distance {dist:.3f})")