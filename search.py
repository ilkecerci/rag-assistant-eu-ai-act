"""Retrieval: search the index directly, without calling any LLM."""
import argparse

import chromadb
from sentence_transformers import SentenceTransformer

from index import MODEL_NAME, DB_PATH, COLLECTION

model = SentenceTransformer(MODEL_NAME)
collection = chromadb.PersistentClient(path=DB_PATH).get_collection(COLLECTION)

STRATEGIES = ["baseline", "body_only", "mixed"]


def search(question, k=5, sections=None):
    """Nearest chunks to the question, optionally restricted to some document sections."""
    query_vec = model.encode(["query: " + question], normalize_embeddings=True)
    where = {"section": {"$in": sections}} if sections else None
    res = collection.query(query_embeddings=query_vec.tolist(), n_results=k, where=where)
    return list(zip(res["documents"][0], res["metadatas"][0], res["distances"][0]))


def retrieve(question, k=5, strategy="baseline"):
    """Retrieval strategies compared in the evaluation.

    baseline:  the k nearest chunks from the whole document
    body_only: the k nearest chunks from articles and annexes only (binding text)
    mixed:     k-1 chunks from articles/annexes plus the single nearest recital
    """
    if strategy == "baseline":
        return search(question, k)
    if strategy == "body_only":
        return search(question, k, sections=["article", "annex"])
    if strategy == "mixed":
        hits = search(question, k - 1, ["article", "annex"]) + search(question, 1, ["recital"])
        return sorted(hits, key=lambda h: h[2])
    raise ValueError(f"Unknown strategy: {strategy}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("question", nargs="*", default=["Which AI practices are prohibited?"])
    parser.add_argument("--strategy", default="baseline", choices=STRATEGIES)
    args = parser.parse_args()

    question = " ".join(args.question)
    print(f"Query: {question}  (strategy: {args.strategy})")
    for doc, meta, dist in retrieve(question, strategy=args.strategy):
        print(f"\n[page {meta['page']}, {meta['section']}] distance={dist:.3f}")
        print(doc[:300], "...")
