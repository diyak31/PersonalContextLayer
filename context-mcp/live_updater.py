"""
PersonalContext — Live Updater

Keeps the context layer fresh by incrementally re-ingesting recent data
on a schedule. Run this alongside the demo app.

Usage:
    python context-mcp/live_updater.py              # default schedule
    python context-mcp/live_updater.py --once       # run once immediately and exit
    python context-mcp/live_updater.py --source gmail --hours 2

Default schedule:
    Every 30 min  — Gmail (last 1 day of emails)
    Every 60 min  — Canvas assignments
    Every 6 hours — Course websites
    Always live   — Google Calendar (fetched directly at query time, no ingest needed)
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import schedule
from rich.console import Console
from rich.rule import Rule

ROOT       = Path(__file__).parent.parent
AGENT_DIR  = ROOT / "agent"
PYTHON     = ROOT / "agent" / ".venv" / "Scripts" / "python.exe"
STATE_FILE = AGENT_DIR / "data" / "last_updated.json"

console = Console()


# ── State tracking ─────────────────────────────────────────────────────────────

def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def mark_updated(source: str):
    state = _load_state()
    state[source] = datetime.now(timezone.utc).isoformat()
    _save_state(state)


# ── Ingest + embed ─────────────────────────────────────────────────────────────

def run_incremental(source: str, hours: int = 24) -> bool:
    """
    Run incremental ingest + embed for one source.
    Returns True on success.
    """
    console.print(f"  [dim]→[/dim] Ingesting [cyan]{source}[/cyan] (last {hours}h)…", end=" ")

    ingest_args = [str(PYTHON), "ingest.py", "--source", source]
    if source == "gmail":
        # --since takes days, convert hours to days (min 1)
        days = max(1, hours // 24)
        ingest_args += ["--since", str(days)]

    result = subprocess.run(
        ingest_args,
        cwd=str(AGENT_DIR),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        console.print(f"[red]✗[/red]")
        if result.stderr:
            console.print(f"  [dim red]{result.stderr[:200]}[/dim red]")
        return False

    # Embed new records (incremental — no --reset)
    embed_result = subprocess.run(
        [str(PYTHON), "embed.py", "--source", source],
        cwd=str(AGENT_DIR),
        capture_output=True,
        text=True,
    )

    if embed_result.returncode != 0:
        console.print(f"[yellow]⚠ ingest ok, embed failed[/yellow]")
        return False

    console.print(f"[green]✓[/green]")
    mark_updated(source)
    return True


# ── Scheduled jobs ─────────────────────────────────────────────────────────────

def job_gmail():
    console.print(Rule("[dim]Gmail refresh[/dim]", style="dim"))
    run_incremental("gmail", hours=24)


def job_canvas():
    console.print(Rule("[dim]Canvas refresh[/dim]", style="dim"))
    run_incremental("canvas", hours=168)  # full pull (Canvas is small)


def job_courses():
    console.print(Rule("[dim]Course websites refresh[/dim]", style="dim"))
    run_incremental("course_websites", hours=168)


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="PersonalContext live updater")
    parser.add_argument("--once",   action="store_true", help="Run all sources once and exit")
    parser.add_argument("--source", help="Run a specific source only")
    parser.add_argument("--hours",  type=int, default=24, help="Lookback window in hours")
    args = parser.parse_args()

    console.print()
    console.print("[bold cyan]PersonalContext Live Updater[/bold cyan]")
    console.print("[dim]Google Calendar is always live — no refresh needed.[/dim]")
    console.print()

    if args.once or args.source:
        sources = [args.source] if args.source else ["gmail", "canvas", "course_websites"]
        for src in sources:
            run_incremental(src, args.hours)
        console.print("\n[green]Done.[/green]")
        return

    # Scheduled mode
    console.print("[dim]Schedule:[/dim]")
    console.print("  Gmail          every 30 min")
    console.print("  Canvas         every 60 min")
    console.print("  Course sites   every 6 hours")
    console.print()
    console.print("[dim]Press Ctrl+C to stop.[/dim]\n")

    # Run once immediately on start
    job_gmail()
    job_canvas()
    job_courses()

    # Then schedule
    schedule.every(30).minutes.do(job_gmail)
    schedule.every(60).minutes.do(job_canvas)
    schedule.every(6).hours.do(job_courses)

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[dim]Updater stopped.[/dim]")
