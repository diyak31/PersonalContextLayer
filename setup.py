#!/usr/bin/env python3
"""
PersonalContext — Setup Wizard

Walks a new user through every setup step:
  environment → API keys → data sources → pipeline → verify

Run from the PersonalAgent root:
    python setup.py
    python setup.py --skip-pipeline   # skip ingest/embed if already built
    python setup.py --check           # just show current status
"""

import argparse
import os
import subprocess
import sys
import json
from pathlib import Path

# ── Bootstrap rich before anything else ───────────────────────────────────────

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    from rich.rule import Rule
    from rich import print as rprint
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "rich", "-q"], check=True)
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    from rich.rule import Rule

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

console = Console(highlight=False)

# ── Paths ──────────────────────────────────────────────────────────────────────

ROOT      = Path(__file__).parent
AGENT_DIR = ROOT / "agent"
ENV_FILE  = AGENT_DIR / ".env"
DB_DIR    = AGENT_DIR / "db"
RAW_DIR   = AGENT_DIR / "data" / "raw"

# Agent venv Python (platform-aware)
if sys.platform == "win32":
    AGENT_PYTHON = ROOT / "agent" / ".venv" / "Scripts" / "python.exe"
else:
    AGENT_PYTHON = ROOT / "agent" / ".venv" / "bin" / "python"


# ── Helpers ────────────────────────────────────────────────────────────────────

def ok(msg: str):    console.print(f"  [bold green]✓[/bold green]  {msg}")
def warn(msg: str):  console.print(f"  [bold yellow]⚠[/bold yellow]  {msg}")
def fail(msg: str):  console.print(f"  [bold red]✗[/bold red]  {msg}")
def info(msg: str):  console.print(f"  [dim]→[/dim]  {msg}")
def step(n: int, total: int, title: str):
    console.print()
    console.print(Rule(f"[bold cyan]Step {n}/{total} — {title}[/bold cyan]", style="cyan"))

def run(cmd: list[str], cwd: Path = None, capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd or ROOT),
        capture_output=capture,
        text=True,
    )

def load_env() -> dict[str, str]:
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env

def save_env(env: dict[str, str]):
    lines = [f"{k}={v}" for k, v in env.items()]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

def jsonl_count(name: str) -> int:
    path = RAW_DIR / name
    if not path.exists():
        return 0
    try:
        return sum(1 for _ in open(path, encoding="utf-8", errors="ignore"))
    except Exception:
        return 0

def chroma_count() -> int:
    try:
        sys.path.insert(0, str(ROOT / "context-mcp"))
        import chromadb
        client = chromadb.PersistentClient(path=str(DB_DIR))
        col = client.get_collection("personal_memory")
        return col.count()
    except Exception:
        return 0


# ══════════════════════════════════════════════════════════════════════════════
# STATUS CHECK  (--check flag)
# ══════════════════════════════════════════════════════════════════════════════

def show_status():
    console.print()
    console.print(Panel("[bold]PersonalContext — Setup Status[/bold]", style="cyan"))

    env = load_env()

    table = Table(show_header=True, header_style="bold dim")
    table.add_column("Component",   width=28)
    table.add_column("Status",      width=18)
    table.add_column("Detail",      width=36)

    # Python venv
    venv_ok = AGENT_PYTHON.exists()
    table.add_row(
        "Agent venv",
        "[green]Ready[/green]" if venv_ok else "[red]Missing[/red]",
        str(AGENT_PYTHON.parent) if venv_ok else "Run: cd agent && uv sync",
    )

    # API keys
    for key, label in [("ANTHROPIC_API_KEY", "Anthropic API key"),
                        ("CANVAS_TOKEN",      "Canvas token"),
                        ("PYTHONIOENCODING",  "UTF-8 encoding")]:
        present = bool(env.get(key) or os.environ.get(key))
        table.add_row(
            label,
            "[green]Set[/green]" if present else "[red]Missing[/red]",
            "agent/.env" if present else f"Add {key}= to agent/.env",
        )

    # OAuth tokens
    for path, label in [
        (ROOT / "gmail-mcp"  / "token.json", "Gmail OAuth"),
        (ROOT / "gcal-mcp"   / "token.json", "Calendar OAuth"),
    ]:
        table.add_row(
            label,
            "[green]Connected[/green]" if path.exists() else "[yellow]Not connected[/yellow]",
            str(path) if path.exists() else f"Run: cd {path.parent.name} && python auth.py",
        )

    # Data pipeline
    sources = [
        ("gmail.jsonl",          "Gmail data"),
        ("gcal.jsonl",           "Calendar data"),
        ("canvas.jsonl",         "Canvas data"),
        ("course_websites.jsonl","Course website data"),
    ]
    for fname, label in sources:
        count = jsonl_count(fname)
        table.add_row(
            label,
            f"[green]{count:,} records[/green]" if count else "[dim]Not ingested[/dim]",
            str(RAW_DIR / fname) if count else "Run: python agent/ingest.py",
        )

    vectors = chroma_count()
    table.add_row(
        "Vector database",
        f"[green]{vectors:,} vectors[/green]" if vectors else "[dim]Not embedded[/dim]",
        str(DB_DIR) if vectors else "Run: python agent/embed.py",
    )

    console.print(table)
    console.print()


# ══════════════════════════════════════════════════════════════════════════════
# SETUP STEPS
# ══════════════════════════════════════════════════════════════════════════════

def step_environment():
    """Check Python version and agent venv."""
    step(1, 6, "Environment")

    # Python version
    major, minor = sys.version_info[:2]
    if major < 3 or minor < 11:
        fail(f"Python 3.11+ required. You have {major}.{minor}.")
        fail("Download from https://python.org/downloads")
        sys.exit(1)
    ok(f"Python {major}.{minor}")

    # Agent venv
    if AGENT_PYTHON.exists():
        ok("Agent virtual environment found")
        return

    warn("Agent venv not found. Creating with uv...")
    info("This installs all dependencies (chromadb, sentence-transformers, etc.)")
    info("May take 2-3 minutes on first run.\n")

    result = run(["uv", "sync"], cwd=AGENT_DIR, capture=False)
    if result.returncode != 0:
        fail("uv sync failed. Is uv installed?")
        info("Install uv: https://docs.astral.sh/uv/getting-started/installation/")
        info("Or: pip install uv")
        sys.exit(1)
    ok("Agent venv created")


def step_api_keys():
    """Collect ANTHROPIC_API_KEY and CANVAS_TOKEN."""
    step(2, 6, "API Keys")

    env = load_env()
    changed = False

    # ANTHROPIC_API_KEY
    existing = env.get("ANTHROPIC_API_KEY", "") or os.environ.get("ANTHROPIC_API_KEY", "")
    if existing:
        ok(f"Anthropic API key found ({existing[:12]}...)")
    else:
        console.print()
        console.print("  Get your key at: [link]https://console.anthropic.com/settings/keys[/link]")
        key = Prompt.ask("  Anthropic API key", password=True)
        if not key.startswith("sk-ant"):
            warn("That doesn't look like an Anthropic key (should start with sk-ant-)")
        env["ANTHROPIC_API_KEY"] = key.strip()
        changed = True
        ok("Anthropic API key saved")

    # CANVAS_TOKEN
    existing_canvas = env.get("CANVAS_TOKEN", "") or os.environ.get("CANVAS_TOKEN", "")
    if existing_canvas:
        ok(f"Canvas token found ({existing_canvas[:8]}...)")
    else:
        console.print()
        console.print("  To get your Canvas token:")
        console.print("  1. Go to [bold]canvas.stanford.edu[/bold] (or your institution's Canvas)")
        console.print("  2. Click [bold]Account → Settings[/bold]")
        console.print("  3. Scroll to [bold]Approved Integrations → New Access Token[/bold]")
        console.print()
        if Confirm.ask("  Do you want to add a Canvas token?", default=True):
            token = Prompt.ask("  Canvas token", password=True)
            env["CANVAS_TOKEN"] = token.strip()
            changed = True
            ok("Canvas token saved")
        else:
            warn("Skipped — Canvas assignments won't be included in context")

    # UTF-8 encoding (Windows)
    if sys.platform == "win32":
        env["PYTHONIOENCODING"] = "utf-8"
        changed = True

    if changed:
        save_env(env)
        ok(f"Saved to {ENV_FILE}")


def step_google_oauth():
    """Run OAuth flows for Gmail and Calendar."""
    step(3, 6, "Google OAuth (Gmail + Calendar)")

    sources = [
        {
            "name":        "Gmail",
            "dir":         ROOT / "gmail-mcp",
            "token":       ROOT / "gmail-mcp" / "token.json",
            "credentials": ROOT / "gmail-mcp" / "credentials.json",
        },
        {
            "name":        "Google Calendar",
            "dir":         ROOT / "gcal-mcp",
            "token":       ROOT / "gcal-mcp" / "token.json",
            "credentials": ROOT / "gcal-mcp" / "credentials.json",
        },
    ]

    any_missing_creds = any(not s["credentials"].exists() for s in sources)

    if any_missing_creds:
        console.print()
        console.print(Panel(
            "[bold]Google Cloud credentials setup[/bold]\n\n"
            "You need a Google Cloud project with Gmail and Calendar APIs enabled.\n\n"
            "[bold]Steps:[/bold]\n"
            "1. Go to [link]https://console.cloud.google.com[/link]\n"
            "2. Create a project (or select an existing one)\n"
            "3. Enable APIs:\n"
            "   • [link]https://console.cloud.google.com/apis/library/gmail.googleapis.com[/link]\n"
            "   • [link]https://console.cloud.google.com/apis/library/calendar-json.googleapis.com[/link]\n"
            "4. Create OAuth credentials:\n"
            "   APIs & Services → Credentials → Create → OAuth client ID → Desktop app\n"
            "5. Download the JSON file as [bold]credentials.json[/bold]",
            title="Google Cloud Setup",
            border_style="yellow",
        ))
        console.print()

    for src in sources:
        if src["token"].exists():
            ok(f"{src['name']}: already connected")
            continue

        console.print()
        console.print(f"  [bold]{src['name']}[/bold] — not yet connected")

        if not src["credentials"].exists():
            console.print(f"  Copy your [bold]credentials.json[/bold] to:")
            console.print(f"  [cyan]{src['credentials']}[/cyan]")
            console.print()
            if not Confirm.ask(f"  credentials.json is in place — connect {src['name']}?", default=False):
                warn(f"Skipped {src['name']}")
                continue

        if not src["credentials"].exists():
            fail(f"credentials.json not found at {src['credentials']}")
            warn(f"Skipping {src['name']}")
            continue

        console.print(f"  Opening browser for {src['name']} OAuth...")
        console.print("  [dim]A browser window will open. Sign in and approve access.[/dim]")
        console.print()

        # Use the venv python that has google-auth-oauthlib installed
        python = str(AGENT_PYTHON) if AGENT_PYTHON.exists() else sys.executable
        result = run(
            [python, str(src["dir"] / "auth.py")],
            cwd=src["dir"],
            capture=False,
        )
        if result.returncode == 0 and src["token"].exists():
            ok(f"{src['name']}: connected ✓")
        else:
            fail(f"{src['name']}: auth failed — check error above")


def step_additional_sources():
    """Prompt for optional sources (Notion, GitHub, etc.)."""
    step(4, 6, "Additional Sources (optional)")

    env = load_env()
    changed = False

    optional = [
        {
            "id":    "NOTION_TOKEN",
            "name":  "Notion",
            "desc":  "Notes, documents, databases",
            "guide": "Notion → Settings → Connections → Develop / manage integrations → New integration → copy Internal Integration Secret",
        },
        {
            "id":    "GITHUB_TOKEN",
            "name":  "GitHub",
            "desc":  "Commits, pull requests, issues",
            "guide": "github.com → Settings → Developer settings → Personal access tokens → Generate new token (read:repo scope)",
        },
    ]

    for src in optional:
        existing = env.get(src["id"], "")
        if existing:
            ok(f"{src['name']}: already configured")
            continue

        console.print()
        if Confirm.ask(f"  Add [bold]{src['name']}[/bold] ({src['desc']})?", default=False):
            console.print(f"  [dim]{src['guide']}[/dim]")
            token = Prompt.ask(f"  {src['name']} token", password=True)
            env[src["id"]] = token.strip()
            changed = True
            ok(f"{src['name']} token saved")
        else:
            info(f"Skipped {src['name']}")

    if changed:
        save_env(env)

    console.print()
    info("You can add more sources later via the Streamlit UI or by editing agent/.env")


def step_pipeline(skip: bool = False):
    """Run ingest → embed → behavioral profile."""
    step(5, 6, "Build Context Layer")

    if skip:
        vectors = chroma_count()
        if vectors > 0:
            ok(f"Skipping pipeline — {vectors:,} vectors already in database")
            return
        warn("--skip-pipeline set but no database found. Running pipeline anyway.")

    python = str(AGENT_PYTHON) if AGENT_PYTHON.exists() else sys.executable

    console.print()
    console.print("  This will ingest your data and build the vector database.")
    console.print("  [dim]Gmail (~2 min) → Calendar → Canvas → Embed (~3 min) → Profile[/dim]")
    console.print()

    if not Confirm.ask("  Run pipeline now?", default=True):
        warn("Skipped — run manually: python agent/ingest.py && python agent/embed.py")
        return

    stages = [
        {
            "label":  "Ingesting Gmail",
            "cmd":    [python, "ingest.py", "--source", "gmail"],
            "cwd":    AGENT_DIR,
            "verify": lambda: jsonl_count("gmail.jsonl"),
            "unit":   "emails",
        },
        {
            "label":  "Ingesting Google Calendar",
            "cmd":    [python, "ingest.py", "--source", "gcal"],
            "cwd":    AGENT_DIR,
            "verify": lambda: jsonl_count("gcal.jsonl"),
            "unit":   "events",
        },
        {
            "label":  "Ingesting Canvas",
            "cmd":    [python, "ingest.py", "--source", "canvas"],
            "cwd":    AGENT_DIR,
            "verify": lambda: jsonl_count("canvas.jsonl"),
            "unit":   "assignments",
        },
        {
            "label":  "Ingesting course websites",
            "cmd":    [python, "ingest.py", "--source", "course_websites"],
            "cwd":    AGENT_DIR,
            "verify": lambda: jsonl_count("course_websites.jsonl"),
            "unit":   "pages",
        },
        {
            "label":  "Embedding vectors",
            "cmd":    [python, "embed.py"],
            "cwd":    AGENT_DIR,
            "verify": chroma_count,
            "unit":   "vectors",
        },
        {
            "label":  "Building behavioral profile",
            "cmd":    [python, "behavioral_profile.py"],
            "cwd":    AGENT_DIR,
            "verify": lambda: 1 if (AGENT_DIR / "data" / "profile.json").exists() else 0,
            "unit":   "",
        },
    ]

    for stage in stages:
        console.print(f"  [dim]→[/dim] {stage['label']}…", end=" ")
        result = run(stage["cmd"], cwd=stage["cwd"], capture=True)
        count = stage["verify"]()
        if count:
            suffix = f"({count:,} {stage['unit']})" if stage["unit"] else ""
            console.print(f"[green]✓[/green] {suffix}")
        else:
            console.print(f"[yellow]⚠ check output[/yellow]")
            if result.stderr:
                console.print(f"    [dim]{result.stderr[:200]}[/dim]")


def step_verify():
    """Final status check and run instructions."""
    step(6, 6, "Verify & Launch")

    vectors = chroma_count()
    gmail   = jsonl_count("gmail.jsonl")
    gcal    = jsonl_count("gcal.jsonl")
    canvas  = jsonl_count("canvas.jsonl")
    profile = (AGENT_DIR / "data" / "profile.json").exists()
    gmail_ok = (ROOT / "gmail-mcp" / "token.json").exists()
    gcal_ok  = (ROOT / "gcal-mcp"  / "token.json").exists()

    console.print()
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(width=30)
    table.add_column(width=20)

    def row(label, value, good):
        color = "green" if good else "yellow"
        table.add_row(label, f"[{color}]{value}[/{color}]")

    row("Gmail",             f"{gmail:,} emails",     gmail > 0)
    row("Google Calendar",   f"{gcal:,} events",      gcal > 0)
    row("Canvas",            f"{canvas:,} assignments",canvas > 0)
    row("Gmail OAuth",       "Connected" if gmail_ok else "Not connected", gmail_ok)
    row("Calendar OAuth",    "Connected" if gcal_ok  else "Not connected", gcal_ok)
    row("Vector database",   f"{vectors:,} vectors",  vectors > 0)
    row("Behavioral profile","Ready" if profile else "Missing", profile)
    console.print(table)
    console.print()

    if vectors > 0:
        console.print(Panel(
            "[bold green]Setup complete![/bold green]\n\n"
            "Run the apps:\n\n"
            "  [bold cyan]Universal demo (VC pitch):[/bold cyan]\n"
            "  streamlit run demo/universal_app.py\n\n"
            "  [bold cyan]Agent builder (developer tool):[/bold cyan]\n"
            "  streamlit run demo/builder_app.py\n\n"
            "  [bold cyan]Platform integrations:[/bold cyan]\n"
            "  streamlit run demo/platforms_app.py\n\n"
            "  [bold cyan]Quick agent test:[/bold cyan]\n"
            "  python agent/orchestrator.py",
            title="PersonalContext",
            border_style="green",
        ))
    else:
        console.print(Panel(
            "[yellow]Setup incomplete — vector database is empty.[/yellow]\n\n"
            "Run the pipeline manually:\n"
            "  python agent/ingest.py\n"
            "  python agent/embed.py\n"
            "  python agent/behavioral_profile.py",
            border_style="yellow",
        ))


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="PersonalContext setup wizard")
    parser.add_argument("--check",         action="store_true", help="Show current status and exit")
    parser.add_argument("--skip-pipeline", action="store_true", help="Skip ingest/embed if already built")
    args = parser.parse_args()

    console.print()
    console.print(Panel(
        "[bold]PersonalContext — Setup Wizard[/bold]\n\n"
        "This wizard will walk you through:\n"
        "  1. Environment check\n"
        "  2. API keys (.env)\n"
        "  3. Google OAuth (Gmail + Calendar)\n"
        "  4. Additional sources (Notion, GitHub, …)\n"
        "  5. Build context layer (ingest → embed → profile)\n"
        "  6. Verify & launch\n\n"
        "[dim]Run with --check to see current status only.[/dim]",
        title="PersonalContext",
        border_style="cyan",
    ))

    if args.check:
        show_status()
        return

    if not Confirm.ask("\n  Ready to start?", default=True):
        console.print("  Run [bold]python setup.py[/bold] when you're ready.")
        return

    step_environment()
    step_api_keys()
    step_google_oauth()
    step_additional_sources()
    step_pipeline(skip=args.skip_pipeline)
    step_verify()


if __name__ == "__main__":
    main()
