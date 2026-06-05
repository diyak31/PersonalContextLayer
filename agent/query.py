"""
Query interface for the personal memory vector database.

Usage (CLI):
    python query.py "what assignments do I have due soon"
    python query.py "emails from professors" --source gmail --n 5
    python query.py "calendar events this week" --source gcal

Usage (as a library):
    from query import search, search_by_source, get_context_for_agent
"""

import argparse
import json
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

AGENT_DIR  = Path(__file__).parent
DB_DIR     = AGENT_DIR / "db"
EMBED_MODEL = "all-MiniLM-L6-v2"

_collection = None


def _get_collection():
    global _collection
    if _collection is None:
        if not DB_DIR.exists():
            raise RuntimeError(
                "No database found. Run `python ingest.py` then `python embed.py` first."
            )
        client = chromadb.PersistentClient(path=str(DB_DIR))
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
        _collection = client.get_collection("personal_memory", embedding_function=ef)
    return _collection


def search(
    query: str,
    n_results: int = 10,
    source: str | None = None,
) -> list[dict]:
    """
    Semantic search across all personal data.

    Args:
        query:     natural language query
        n_results: number of results to return
        source:    filter by source (gmail/gcal/canvas/course_websites/purchases)

    Returns:
        list of dicts with keys: text, metadata, distance
    """
    col = _get_collection()
    where = {"source": source} if source else None

    results = col.query(
        query_texts=[query],
        n_results=min(n_results, col.count()),
        where=where,
    )

    output = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        output.append({"text": doc, "metadata": meta, "distance": round(dist, 3)})
    return output


def search_by_source(source: str, n_results: int = 20) -> list[dict]:
    """Get recent items from a specific source without semantic filtering."""
    col = _get_collection()
    results = col.get(where={"source": source}, limit=n_results)
    output = []
    for doc, meta in zip(results["documents"], results["metadatas"]):
        output.append({"text": doc, "metadata": meta})
    return output


def get_context_for_agent(query: str, n_results: int = 8) -> str:
    """
    Returns a formatted context string ready to inject into an LLM prompt.
    Used by the agent orchestrator at query time.
    """
    results = search(query, n_results=n_results)
    if not results:
        return "No relevant personal data found."

    lines = ["Relevant personal context:\n"]
    for i, r in enumerate(results, 1):
        source = r["metadata"].get("source", "unknown")
        lines.append(f"[{i}] ({source}) {r['text'][:400]}")
        lines.append("")
    return "\n".join(lines)


def stats() -> dict:
    """Return stats about the vector database."""
    col = _get_collection()
    total = col.count()
    by_source = {}
    for source in ["gmail", "gcal", "canvas", "course_websites", "purchases"]:
        try:
            count = len(col.get(where={"source": source})["ids"])
            if count:
                by_source[source] = count
        except Exception:
            pass
    return {"total": total, "by_source": by_source}


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Query personal memory")
    parser.add_argument("query", nargs="?", help="Search query")
    parser.add_argument("--source", help="Filter by source")
    parser.add_argument("--n", type=int, default=5, help="Number of results")
    parser.add_argument("--stats", action="store_true", help="Show DB stats")
    args = parser.parse_args()

    if args.stats or not args.query:
        s = stats()
        table = Table(title="Personal Memory DB")
        table.add_column("Source", style="cyan")
        table.add_column("Vectors", justify="right", style="green")
        for src, count in s["by_source"].items():
            table.add_row(src, str(count))
        table.add_row("[bold]TOTAL[/bold]", f"[bold]{s['total']}[/bold]")
        console.print(table)
        return

    results = search(args.query, n_results=args.n, source=args.source)
    console.print(f"\n[bold]Results for:[/bold] {args.query}\n")
    for i, r in enumerate(results, 1):
        src  = r["metadata"].get("source", "?")
        dist = r["distance"]
        console.print(Panel(
            r["text"][:500],
            title=f"[{i}] {src}  (similarity: {1 - dist:.2f})",
            border_style="blue",
        ))


if __name__ == "__main__":
    main()
