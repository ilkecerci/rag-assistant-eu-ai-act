"""Step 1: Load the EU AI Act PDF and split it into overlapping chunks."""
from collections import Counter
from pypdf import PdfReader 
import re

PDF_PATH = "data/ai_act.pdf"


def load_pdf(path):
    """Return one dict per page with its page number and raw text."""
    reader = PdfReader(path)
    return [{"page": i + 1, "text": page.extract_text() or ""}
            for i, page in enumerate(reader.pages)]


"""def most_common_lines(pages, top_n=10):
    Count how many pages each line appears on; repeated lines are likely headers/footers.
    counts = Counter()
    for p in pages:
        lines = {line.strip() for line in p["text"].splitlines() if line.strip()}
        counts.update(lines)
    return counts.most_common(top_n)"""

PAGE_NUMBER = re.compile(r"\s*\d+/\d+$")


def line_key(line):
    """Strip a trailing page number like '33/144' so footers on different pages match."""
    return PAGE_NUMBER.sub("", line.strip())

def line_page_counts(pages):
    """Count on how many pages each distinct line (ignoring page numbers) appears."""
    counts = Counter()
    for p in pages:
        counts.update({line_key(line) for line in p["text"].splitlines() if line.strip()})
    return counts


def remove_repeated_lines(pages, min_ratio=0.3):
    """Drop lines that appear on at least min_ratio of all pages (running headers/footers)."""
    counts = line_page_counts(pages)
    threshold = len(pages) * min_ratio
    repeated = {key for key, n in counts.items() if n >= threshold}
    cleaned = []
    for p in pages:
        kept = [line for line in p["text"].splitlines() if line_key(line) not in repeated]
        cleaned.append({"page": p["page"], "text": "\n".join(kept)})
    return cleaned, repeated

def find_marker(pages, pattern, start_page=1):
    """Return (page, offset) of the first regex match at or after start_page, in whitespace-normalized text."""
    for p in pages:
        if p["page"] < start_page:
            continue
        text = " ".join(p["text"].split())
        match = re.search(pattern, text)
        if match:
            return (p["page"], match.start())
    raise ValueError(f"Marker not found: {pattern}")


def section_of(page, offset, body_start, annex_start):
    """Classify a position in the document; tuples compare page first, then offset."""
    if (page, offset) < body_start:
        return "recital"
    if (page, offset) < annex_start:
        return "article"
    return "annex"

def chunk_pages(pages, body_start, annex_start, chunk_size=1000, overlap=200):
    """Split each page into chunks of ~chunk_size characters, cutting only at word boundaries."""
    chunks = []
    for p in pages:
        text = " ".join(p["text"].split())  # normalize whitespace
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            if end < len(text):
                last_space = text.rfind(" ", start, end)
                if last_space > start:
                    end = last_space  # do not cut a word in half
            chunks.append({
                "id": f"p{p['page']}_{start}",
                "page": p["page"],
                "section": section_of(p["page"], start, body_start, annex_start),
                "text": text[start:end],
            })
            if end == len(text):
                break
            # Step back by `overlap` characters, then move forward to the next word start
            new_start = end - overlap
            space = text.find(" ", new_start, end)
            new_start = space + 1 if space != -1 else end
            start = max(new_start, start + 1)  # always make progress
    return chunks


if __name__ == "__main__":
    pages = load_pdf(PDF_PATH)
    pages, removed = remove_repeated_lines(pages)
    body_start = find_marker(pages, r"HAVE ADOPTED THIS REGULATION")
    annex_start = find_marker(pages, r"\bANNEX I\b", start_page=body_start[0])
    print(f"Articles start at page {body_start[0]}, annexes at page {annex_start[0]}")

    chunks = chunk_pages(pages, body_start, annex_start)
    print(Counter(c["section"] for c in chunks))
    lengths = [len(c["text"]) for c in chunks]
    print(f"{len(pages)} pages -> {len(chunks)} chunks")
    print(f"Chunk length: min {min(lengths)}, avg {sum(lengths) // len(lengths)}, max {max(lengths)}")

    print("\nFirst and last lines of page 10 after cleaning:")
    lines = [line for line in pages[9]["text"].splitlines() if line.strip()]
    for line in lines[:3] + ["..."] + lines[-3:]:
        print("  ", line[:80])
        