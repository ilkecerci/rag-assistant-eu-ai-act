"""Retrieval check: search the index directly, without calling any LLM."""
import sys

import chromadb
from sentence_transformers import SentenceTransformer

from index import MODEL_NAME, DB_PATH, COLLECTION

model = SentenceTransformer(MODEL_NAME)
collection = chromadb.PersistentClient(path=DB_PATH).get_collection(COLLECTION)


def search(question, k=5):
    query_vec = model.encode(["query: " + question], normalize_embeddings=True)
    res = collection.query(query_embeddings=query_vec.tolist(), n_results=k)
    return list(zip(res["documents"][0], res["metadatas"][0], res["distances"][0]))


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "Which AI practices are prohibited?"
    print(f"Query: {question}")
    for doc, meta, dist in search(question):
        print(f"\n[page {meta['page']}] distance={dist:.3f}")
        print(doc[:300], "...")