"""Step 4: Serve the RAG pipeline as a REST API."""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from fastapi.staticfiles import StaticFiles
from rag import answer, NOT_FOUND  # importing rag loads the models once, at startup

app = FastAPI(title="EU AI Act RAG Assistant")


class Question(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)


class Source(BaseModel):
    passage: int
    page: int
    distance: float
    text: str


class Answer(BaseModel):
    answer: str
    found: bool
    sources: list[Source]


@app.get("/health")
def health():
    """Lets other services check that the API is up."""
    return {"status": "ok"}


@app.post("/ask", response_model=Answer)
def ask(q: Question):
    try:
        text, hits = answer(q.question)
    except Exception as exc:  # e.g. the LLM provider is down or rate-limited
        raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}")

    found = text.strip() != NOT_FOUND
    sources = [
        Source(passage=i, page=meta["page"], distance=round(dist, 3), text=doc)
        for i, (doc, meta, dist) in enumerate(hits, start=1)
    ] if found else []
    return Answer(answer=text, found=found, sources=sources)

# Mounted last so that /ask, /health and /docs take priority over static files
app.mount("/pdf", StaticFiles(directory="data"), name="pdf")
app.mount("/", StaticFiles(directory="static", html=True), name="static")