"""Step 2: Embed the chunks and store them in a persistent ChromaDB collection."""
import chromadb
from sentence_transformers import SentenceTransformer

from ingest import PDF_PATH, load_pdf, remove_repeated_lines, chunk_pages

MODEL_NAME = "intfloat/multilingual-e5-base"
DB_PATH = "chroma_db"
COLLECTION = "ai_act"


def build_index():
    pages, _ = remove_repeated_lines(load_pdf(PDF_PATH))
    chunks = chunk_pages(pages)

    model = SentenceTransformer(MODEL_NAME)
    # e5 models expect "passage: " before documents and "query: " before questions
    texts = ["passage: " + c["text"] for c in chunks]
    embeddings = model.encode(texts, batch_size=32,
                              normalize_embeddings=True, show_progress_bar=True)
    print(f"Embedding matrix shape: {embeddings.shape}")

    client = chromadb.PersistentClient(path=DB_PATH)
    try:
        client.delete_collection(COLLECTION)  # rebuild from scratch on every run
    except Exception:
        pass  # collection did not exist yet

    collection = client.create_collection(COLLECTION)
    collection.add(
        ids=[c["id"] for c in chunks],
        embeddings=embeddings.tolist(),
        documents=[c["text"] for c in chunks],
        metadatas=[{"page": c["page"]} for c in chunks],
    )
    print(f"Stored {collection.count()} chunks in '{DB_PATH}/'")


if __name__ == "__main__":
    build_index()