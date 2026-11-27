"""Step 5: Evaluate retrieval (and optionally answers) on a fixed question set."""
import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

from ingest import PDF_PATH, load_pdf
from search import retrieve, STRATEGIES

QUESTIONS_PATH = Path("eval/questions.json")
RESULTS_DIR = Path("eval/results")
TOP_K = 5
CITATION = re.compile(r"\[(\d+)\]")


def build_section_index(pages):
    """Locate every Article and Annex heading; return ({name: (first_page, last_page)}, body_start_page)."""
    starts = []
    next_article = 1
    body_start = None
    for p in pages:
        if body_start is None and "HAVE ADOPTED THIS REGULATION" in p["text"]:
            body_start = p["page"]  # recitals end here, binding articles begin
        if body_start is None:
            continue
        for line in p["text"].splitlines():
            line = line.strip()
            # Accept "Article N" only in sequence, so inline references are not mistaken for headings
            if line == f"Article {next_article}":
                starts.append((line, p["page"]))
                next_article += 1
            elif next_article > 113 and re.fullmatch(r"ANNEX [IVX]+", line):
                name = line.replace("ANNEX", "Annex")
                if name not in {n for n, _ in starts}:
                    starts.append((name, p["page"]))

    last_page = pages[-1]["page"]
    sections = {}
    for i, (name, first) in enumerate(starts):
        last = starts[i + 1][1] if i + 1 < len(starts) else last_page
        sections[name] = (first, last)
    return sections, body_start


def evaluate(use_llm, label, strategy):
    questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    pages = load_pdf(PDF_PATH)
    sections, body_start = build_section_index(pages)
    n_articles = sum(name.startswith("Article") for name in sections)
    print(f"Found {n_articles} articles and {len(sections) - n_articles} annexes; "
          f"articles start on page {body_start}")
    print(f"Retrieval strategy: {strategy}   (section tags: R=recital, A=article, X=annex)\n")

    if use_llm:
        from rag import answer, NOT_FOUND

    rows = []
    for q in questions:
        hits = retrieve(q["question"], k=TOP_K, strategy=strategy)
        pages_found = [meta["page"] for _, meta, _ in hits]
        section_tags = "".join({"recital": "R", "article": "A", "annex": "X"}[meta["section"]] for _, meta, _ in hits)
        row = {"id": q["id"], "type": q["type"], "lang": q["lang"],
               "question": q["question"], "retrieved_pages": pages_found,
               "retrieved_sections": section_tags}

        if q["type"] == "in_scope":
            missing = [name for name in q["expected"] if name not in sections]
            if missing:
                print(f"  WARNING q{q['id']}: {missing} not found in the PDF index")
            ranges = [sections[name] for name in q["expected"] if name in sections]
            row["expected"] = ", ".join(f"{n} (p.{sections[n][0]}-{sections[n][1]})"
                                        for n in q["expected"] if n in sections)
            # A hit needs a chunk from the expected article/annex itself, not a recital on a shared page
            row["hit"] = any(first <= meta["page"] <= last and meta["section"] != "recital"
                             for _, meta, _ in hits for first, last in ranges)
            row["body_share"] = sum(meta["section"] != "recital" for _, meta, _ in hits) / len(hits)

        if use_llm:
            try:
                text, used_hits = answer(q["question"], strategy=strategy)
            except Exception as exc:  # record the failure and keep going
                print(f"  ERROR q{q['id']}: {exc}")
                row["error"] = str(exc)
                rows.append(row)
                continue
            found = text.strip() != NOT_FOUND
            cited = {int(n) for n in CITATION.findall(text)}
            row["found"] = found
            row["found_ok"] = found == (q["type"] == "in_scope")
            row["bad_citations"] = sorted(n for n in cited if n < 1 or n > len(used_hits))
            row["answer"] = text
            if q.get("must_contain"):
                # The answer must state every required fact; a refusal is safer than a wrong answer
                # Normalize Unicode spaces first: the model writes e.g. "2\u202fFebruary" (narrow no-break space)
                plain = " ".join(text.split())
                has_facts = all(re.search(p, plain, re.IGNORECASE) for p in q["must_contain"])
                row["fact_check"] = "refused" if not found else ("correct" if has_facts else "wrong")

        rows.append(row)
        status = "HIT " if row.get("hit") else ("MISS" if q["type"] == "in_scope" else "----")
        print(f"q{q['id']:>2} {status} {section_tags} pages={pages_found}  expected={row.get('expected', '-')}")

    # Summary
    in_scope = [r for r in rows if r["type"] == "in_scope"]
    hits = sum(r["hit"] for r in in_scope)
    body = sum(r["body_share"] for r in in_scope) / len(in_scope)
    print(f"\nRetrieval hit@{TOP_K}: {hits}/{len(in_scope)}")
    print(f"Share of retrieved chunks from articles/annexes: {body:.0%}")
    if use_llm:
        answered = [r for r in rows if "error" not in r]
        print(f"Correct answer/refusal decision: {sum(r['found_ok'] for r in answered)}/{len(answered)}")
        print(f"Answers with invalid citations: {sum(bool(r['bad_citations']) for r in answered)}")
        checked = [r for r in answered if r.get("fact_check")]
        if checked:
            c = Counter(r["fact_check"] for r in checked)
            print(f"Fact-checked answers ({len(checked)}): correct {c['correct']}, "
                  f"refused {c['refused']}, WRONG {c['wrong']}")
        unsafe = sum(r["found"] for r in answered if r["type"] != "in_scope")
        print(f"Out-of-scope/trap questions answered (should be 0): {unsafe}")
        if len(answered) < len(rows):
            print(f"Failed questions (excluded above): {len(rows) - len(answered)}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"{label}.csv"
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, restval="")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved results to {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true", help="also generate answers (calls the LLM API)")
    parser.add_argument("--strategy", default="baseline", choices=STRATEGIES)
    parser.add_argument("--label", default=None, help="name of the results file (default: the strategy)")
    args = parser.parse_args()
    evaluate(args.llm, args.label or args.strategy, args.strategy)