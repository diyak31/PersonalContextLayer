"""
Evaluation suite for the PersonalContext layer.

Measures three things per test case:
  1. Specificity     — count of named entities / specific dates / course codes
  2. Self-sufficient — did the agent answer without asking for more info?
  3. Quality         — LLM-as-judge score 1–10

Run:
    cd PersonalAgent
    python eval/eval_suite.py
    python eval/eval_suite.py --cases scheduling email   # run specific cases
    python eval/eval_suite.py --json                     # machine-readable output
"""

import argparse
import json
import re
import sys
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

load_dotenv(Path(__file__).parent.parent / "agent" / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))

from agents import naive_agent, enhanced_agent

console = Console()
judge   = Anthropic()

# ── Test cases ─────────────────────────────────────────────────────────────────

TEST_CASES = [
    {
        "id":   "scheduling",
        "task": "Find me a 2-hour focused study block for my CS231N final this week.",
        "description": "Scheduling — requires calendar + course deadline context",
    },
    {
        "id":   "email",
        "task": "Draft an email to my professor asking for a short extension on my CS231N project.",
        "description": "Email drafting — requires communication style + course context",
    },
    {
        "id":   "planning",
        "task": "What should I prioritize this week given my deadlines and commitments?",
        "description": "Week planning — requires full context across all sources",
    },
    {
        "id":   "contacts",
        "task": "Who do I email most often and what do we usually talk about?",
        "description": "Contact recall — requires Gmail behavioral data",
    },
    {
        "id":   "spending",
        "task": "What have I been spending money on lately?",
        "description": "Purchase recall — requires purchases data",
    },
]


# ── Scoring functions ──────────────────────────────────────────────────────────

def count_specifics(text: str) -> int:
    """Count named entities, times, dates, amounts in a response."""
    patterns = [
        r'\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b',
        r'\b\d{1,2}:\d{2}\s*(am|pm|AM|PM)?\b',
        r'\b(January|February|March|April|May|June|July|August|'
        r'September|October|November|December)\b',
        r'\bCS\s*\d{3}[A-Z]?\b',
        r'\$\d+',
        r'\b\d+\s*(days?|hours?|weeks?)\b',
    ]
    return sum(len(re.findall(p, text, re.IGNORECASE)) for p in patterns)


def asks_for_info(text: str) -> bool:
    """
    Ask Claude Haiku whether this response requests information that a
    well-informed personal assistant should already know.
    """
    response = judge.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=10,
        messages=[{
            "role": "user",
            "content": (
                "Does this personal assistant response ask the user for information "
                "a personal assistant should already know (schedule, courses, preferences, name)? "
                "Answer YES or NO only.\n\n"
                f"Response: {text[:600]}"
            ),
        }],
    )
    return "YES" in response.content[0].text.upper()


def quality_score(task: str, response: str, has_context: bool) -> int:
    """LLM-as-judge: rate response 1–10 for a personal assistant task."""
    context_note = (
        "had access to the user's personal data (emails, calendar, assignments)"
        if has_context
        else "had NO personal data"
    )
    result = judge.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=10,
        messages=[{
            "role": "user",
            "content": (
                f"Rate this personal assistant response 1-10.\n"
                f"The assistant {context_note}.\n\n"
                f"Task: {task}\n"
                f"Response: {response[:600]}\n\n"
                "Scoring rules:\n"
                "- PENALISE heavily (max 4) if the response tells the user HOW to find "
                "information themselves instead of just answering\n"
                "- PENALISE (max 5) if the response asks the user for info a personal "
                "assistant should already know\n"
                "- REWARD responses that give specific names, dates, times, or amounts\n"
                "- REWARD responses that answer directly without caveats or redirection\n"
                "A vague but well-written answer is worse than a specific direct answer.\n"
                "Reply with a single integer 1-10."
            ),
        }],
    )
    try:
        return int(re.search(r"\d+", result.content[0].text).group())
    except Exception:
        return 5


# ── Runner ─────────────────────────────────────────────────────────────────────

def run_case(case: dict) -> dict:
    task = case["task"]

    console.print(f"\n[bold cyan]Running:[/bold cyan] {case['id']} — {case['description']}")

    console.print("  [dim]→ naive agent[/dim]")
    naive_resp = naive_agent(task)

    console.print("  [dim]→ enhanced agent[/dim]")
    enhanced_resp, context = enhanced_agent(task)

    console.print("  [dim]→ scoring[/dim]")
    return {
        "id":          case["id"],
        "description": case["description"],
        "task":        task,
        "naive": {
            "response":     naive_resp,
            "specificity":  count_specifics(naive_resp),
            "asks_for_info": asks_for_info(naive_resp),
            "quality":      quality_score(task, naive_resp, has_context=False),
        },
        "enhanced": {
            "response":        enhanced_resp,
            "specificity":     count_specifics(enhanced_resp),
            "asks_for_info":   asks_for_info(enhanced_resp),
            "quality":         quality_score(task, enhanced_resp, has_context=True),
            "memories_used":   len(context.get("relevant_memories", [])),
            "deadlines_found": len(context.get("deadlines", [])),
        },
    }


def print_summary(results: list[dict]):
    table = Table(title="PersonalContext Eval — Summary", border_style="blue")
    table.add_column("Case",        style="cyan",  width=12)
    table.add_column("Naive qual",  justify="center")
    table.add_column("Enh. qual",   justify="center")
    table.add_column("Δ quality",   justify="center")
    table.add_column("Naive spec",  justify="center")
    table.add_column("Enh. spec",   justify="center")
    table.add_column("Naive asks?", justify="center")
    table.add_column("Enh. asks?",  justify="center")

    for r in results:
        n, e = r["naive"], r["enhanced"]
        dq   = e["quality"] - n["quality"]
        dq_s = f"[green]+{dq}[/green]" if dq > 0 else f"[red]{dq}[/red]"
        table.add_row(
            r["id"],
            str(n["quality"]),
            str(e["quality"]),
            dq_s,
            str(n["specificity"]),
            str(e["specificity"]),
            "[red]Yes[/red]" if n["asks_for_info"] else "[green]No[/green]",
            "[red]Yes[/red]" if e["asks_for_info"] else "[green]No[/green]",
        )

    avg_n = sum(r["naive"]["quality"]    for r in results) / len(results)
    avg_e = sum(r["enhanced"]["quality"] for r in results) / len(results)
    spec_n = sum(r["naive"]["specificity"]    for r in results)
    spec_e = sum(r["enhanced"]["specificity"] for r in results)
    asks_n = sum(1 for r in results if r["naive"]["asks_for_info"])
    asks_e = sum(1 for r in results if r["enhanced"]["asks_for_info"])

    table.add_section()
    table.add_row(
        "[bold]AVERAGE[/bold]",
        f"[bold]{avg_n:.1f}[/bold]",
        f"[bold]{avg_e:.1f}[/bold]",
        f"[bold green]+{avg_e - avg_n:.1f}[/bold green]" if avg_e > avg_n
            else f"[bold red]{avg_e - avg_n:.1f}[/bold red]",
        f"[bold]{spec_n}[/bold]",
        f"[bold]{spec_e}[/bold]",
        f"[bold]{asks_n}/{len(results)}[/bold]",
        f"[bold]{asks_e}/{len(results)}[/bold]",
    )

    console.print()
    console.print(table)
    console.print()
    console.print(
        f"[bold]Quality lift:[/bold] {avg_n:.1f} → {avg_e:.1f}  "
        f"([green]+{avg_e - avg_n:.1f} pts[/green])\n"
        f"[bold]Specificity lift:[/bold] {spec_n} → {spec_e} entities  "
        f"([green]+{spec_e - spec_n}[/green])\n"
        f"[bold]Unnecessary clarifications:[/bold] "
        f"naive {asks_n}/{len(results)}, enhanced {asks_e}/{len(results)}"
    )


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Evaluate PersonalContext layer")
    parser.add_argument("--cases", nargs="*", help="IDs of cases to run (default: all)")
    parser.add_argument("--json",  action="store_true", help="Print results as JSON")
    args = parser.parse_args()

    cases = TEST_CASES
    if args.cases:
        cases = [c for c in TEST_CASES if c["id"] in args.cases]
        if not cases:
            console.print(f"[red]No matching cases. Available: {[c['id'] for c in TEST_CASES]}[/red]")
            sys.exit(1)

    results = [run_case(c) for c in cases]

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print_summary(results)


if __name__ == "__main__":
    main()
