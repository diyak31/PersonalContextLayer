"""
Embedding pipeline — reads raw JSONL files, chunks them, and stores
in a local ChromaDB vector database.

Usage:
    python embed.py           # embed all raw data
    python embed.py --reset   # wipe DB and re-embed everything
"""

import argparse
import json
import re
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions
from rich.console import Console
from rich.progress import track

console = Console()

AGENT_DIR = Path(__file__).parent
RAW_DIR   = AGENT_DIR / "data" / "raw"
DB_DIR    = AGENT_DIR / "db"

# Use local sentence-transformers model (downloads ~90MB on first run)
EMBED_MODEL = "all-MiniLM-L6-v2"


def get_db(reset: bool = False) -> chromadb.ClientAPI:
    if reset and DB_DIR.exists():
        import shutil
        shutil.rmtree(DB_DIR)
        console.print("[yellow]DB wiped.[/yellow]")
    DB_DIR.mkdir(exist_ok=True)
    return chromadb.PersistentClient(path=str(DB_DIR))


def get_collection(client: chromadb.ClientAPI, reset: bool = False):
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
    if reset:
        try:
            client.delete_collection("personal_memory")
        except Exception:
            pass
    return client.get_or_create_collection(
        name="personal_memory",
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )


# ── Chunkers ─────────────────────────────────────────────────────────────────

def _chunk_gmail(records: list[dict]) -> tuple[list[str], list[dict], list[str]]:
    docs, metas, ids = [], [], []
    for r in records:
        label   = r.get("label", "inbox")
        subject = r.get("subject", "")
        sender  = r.get("from", "")
        date    = r.get("date", "")
        snippet = r.get("snippet", "")
        body    = r.get("body", "")

        text = f"Email ({label})\nFrom: {sender}\nSubject: {subject}\nDate: {date}\n\n{body or snippet}"

        docs.append(text[:1500])
        metas.append({
            "source": "gmail",
            "label": label,
            "from": sender[:100],
            "subject": subject[:200],
            "date": date[:50],
        })
        ids.append(f"gmail_{r['id']}")
    return docs, metas, ids


def _chunk_gcal(records: list[dict]) -> tuple[list[str], list[dict], list[str]]:
    docs, metas, ids = [], [], []
    for r in records:
        attendees = ", ".join(r.get("attendees", []))
        text = (
            f"Calendar event: {r.get('title', '')}\n"
            f"Calendar: {r.get('calendar', '')}\n"
            f"Start: {r.get('start', '')}\n"
            f"End: {r.get('end', '')}\n"
            f"Location: {r.get('location', '')}\n"
            f"Attendees: {attendees}\n"
            f"Description: {r.get('description', '')}"
        )
        docs.append(text[:1000])
        metas.append({
            "source": "gcal",
            "calendar": r.get("calendar", "")[:100],
            "title": r.get("title", "")[:200],
            "start": r.get("start", "")[:50],
            "recurring": str(r.get("recurring", False)),
        })
        ids.append(f"gcal_{r['id']}")
    return docs, metas, ids


def _chunk_canvas(records: list[dict]) -> tuple[list[str], list[dict], list[str]]:
    docs, metas, ids = [], [], []
    for r in records:
        if r.get("type") == "course":
            text = f"Canvas course: {r.get('name', '')}"
        else:
            text = (
                f"Assignment: {r.get('name', '')}\n"
                f"Course: {r.get('course', '')}\n"
                f"Due: {r.get('due_at', 'No due date')}\n"
                f"Points: {r.get('points_possible', '')}\n"
                f"{r.get('description', '')}"
            )
        docs.append(text[:800])
        metas.append({
            "source": "canvas",
            "type": r.get("type", ""),
            "course": r.get("course", r.get("name", ""))[:100],
            "due_at": (r.get("due_at") or "")[:50],
        })
        ids.append(r["id"])
    return docs, metas, ids


def _chunk_courses(records: list[dict]) -> tuple[list[str], list[dict], list[str]]:
    docs, metas, ids = [], [], []
    for r in records:
        # Split long course pages into paragraphs
        content = r.get("content", "")
        paragraphs = [p.strip() for p in re.split(r"\n{2,}", content) if len(p.strip()) > 80]

        for i, para in enumerate(paragraphs):
            docs.append(f"[{r['course_name']}] {para[:800]}")
            metas.append({
                "source": "course_websites",
                "course": r.get("course", ""),
                "course_name": r.get("course_name", ""),
                "url": r.get("url", ""),
            })
            ids.append(f"{r['id']}_chunk{i}")
    return docs, metas, ids


def _chunk_purchases(records: list[dict]) -> tuple[list[str], list[dict], list[str]]:
    docs, metas, ids = [], [], []
    for r in records:
        text = (
            f"Purchase from {r.get('merchant', 'Unknown')}\n"
            f"Date: {r.get('date', '')}\n"
            f"Amount: {r.get('amount', 'unknown')}\n"
            f"Subject: {r.get('subject', '')}\n"
            f"{r.get('snippet', '')}"
        )
        docs.append(text[:600])
        metas.append({
            "source": "purchases",
            "merchant": r.get("merchant", "")[:50],
            "amount": r.get("amount", "")[:20] if r.get("amount") else "",
            "date": r.get("date", "")[:50],
        })
        ids.append(f"purchase_{r['id']}")
    return docs, metas, ids


CHUNKERS = {
    "gmail":           _chunk_gmail,
    "gcal":            _chunk_gcal,
    "canvas":          _chunk_canvas,
    "course_websites": _chunk_courses,
    "purchases":       _chunk_purchases,
}


# ── Embed loop ────────────────────────────────────────────────────────────────

def embed_file(source: str, collection, batch_size: int = 64):
    path = RAW_DIR / f"{source}.jsonl"
    if not path.exists():
        console.print(f"  [dim]Skipping {source} (no raw file)[/dim]")
        return

    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    chunker = CHUNKERS.get(source)
    if not chunker:
        console.print(f"  [yellow]⚠[/yellow] No chunker for {source}")
        return

    docs, metas, ids = chunker(records)
    if not docs:
        return

    # Deduplicate IDs
    seen = set()
    clean_docs, clean_metas, clean_ids = [], [], []
    for doc, meta, doc_id in zip(docs, metas, ids):
        if doc_id not in seen:
            seen.add(doc_id)
            clean_docs.append(doc)
            clean_metas.append(meta)
            clean_ids.append(doc_id)

    # Upsert in batches
    total = len(clean_docs)
    for i in track(range(0, total, batch_size), description=f"  {source}...", console=console):
        batch_docs  = clean_docs[i:i+batch_size]
        batch_metas = clean_metas[i:i+batch_size]
        batch_ids   = clean_ids[i:i+batch_size]
        collection.upsert(documents=batch_docs, metadatas=batch_metas, ids=batch_ids)

    console.print(f"  [green]✓[/green] {source}: {total} chunks embedded")


def main():
    parser = argparse.ArgumentParser(description="Embed personal data into ChromaDB")
    parser.add_argument("--reset", action="store_true", help="Wipe and rebuild the DB")
    parser.add_argument("--source", default="all",
                        help="Source to embed (gmail/gcal/canvas/course_websites/purchases/all)")
    args = parser.parse_args()

    console.print(f"\n[bold blue]Personal Agent — Embedding Pipeline[/bold blue]")
    console.print(f"Model: [cyan]{EMBED_MODEL}[/cyan]  |  DB: [cyan]{DB_DIR}[/cyan]\n")

    client     = get_db(reset=args.reset)
    collection = get_collection(client, reset=args.reset)

    sources = list(CHUNKERS.keys()) if args.source == "all" else [args.source]
    for source in sources:
        embed_file(source, collection)

    count = collection.count()
    console.print(f"\n[bold green]✓ Done.[/bold green] Total vectors in DB: [cyan]{count}[/cyan]")
    console.print("Next: run [cyan]python query.py[/cyan] to search your memory.\n")


if __name__ == "__main__":
    main()
