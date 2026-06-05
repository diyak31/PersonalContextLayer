"""
Personal Agent Orchestrator
----------------------------
Answers any question about your digital life by combining:
  1. Long-term memory  — semantic search over ChromaDB (emails, calendar, etc.)
  2. Live tools        — real-time data from Gmail, GCal, Canvas, course websites
  3. Behavioral profile — who you are and how you work

Usage:
    python orchestrator.py                    # interactive chat
    python orchestrator.py "what's due soon"  # single question
"""

import argparse
import json
import os
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from rich.console import Console

load_dotenv(Path(__file__).parent / ".env", override=True)
from rich.markdown import Markdown
from rich.panel import Panel

# ── Paths ─────────────────────────────────────────────────────────────────────
AGENT_DIR   = Path(__file__).parent
PARENT_DIR  = AGENT_DIR.parent
sys.path.insert(0, str(AGENT_DIR))

console = Console()

# ── Live tool implementations (direct API calls, no MCP dependency) ───────────

import base64
import re
import httpx
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

GMAIL_TOKEN = PARENT_DIR / "gmail-mcp" / "token.json"
GCAL_TOKEN  = PARENT_DIR / "gcal-mcp"  / "token.json"


def _gmail_creds():
    creds = Credentials.from_authorized_user_file(str(GMAIL_TOKEN),
        ["https://www.googleapis.com/auth/gmail.readonly",
         "https://www.googleapis.com/auth/gmail.send",
         "https://www.googleapis.com/auth/gmail.modify"])
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def _gcal_creds():
    creds = Credentials.from_authorized_user_file(str(GCAL_TOKEN),
        ["https://www.googleapis.com/auth/calendar.readonly",
         "https://www.googleapis.com/auth/calendar.events"])
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def _hdr(headers, name):
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _gmail_search(query: str, max_results: int = 10) -> str:
    svc = build("gmail", "v1", credentials=_gmail_creds())
    result = svc.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    msgs = result.get("messages", [])
    if not msgs:
        return f"No emails found for: {query}"
    lines = []
    for msg in msgs:
        m = svc.users().messages().get(
            userId="me", id=msg["id"], format="metadata",
            metadataHeaders=["From", "Subject", "Date"]
        ).execute()
        hdrs = m.get("payload", {}).get("headers", [])
        lines.append(f"From: {_hdr(hdrs,'From')}\nSubject: {_hdr(hdrs,'Subject')}\nDate: {_hdr(hdrs,'Date')}\nSnippet: {m.get('snippet','')}\n")
    return "\n".join(lines)


def _gcal_upcoming(days_ahead: int = 14) -> str:
    svc = build("calendar", "v3", credentials=_gcal_creds())
    now = datetime.now(timezone.utc)
    future = now + timedelta(days=days_ahead)
    result = svc.events().list(
        calendarId="primary", timeMin=now.isoformat(), timeMax=future.isoformat(),
        maxResults=20, singleEvents=True, orderBy="startTime"
    ).execute()
    events = result.get("items", [])
    if not events:
        return f"No events in the next {days_ahead} days."
    lines = []
    for e in events:
        start = e.get("start", {}).get("dateTime") or e.get("start", {}).get("date", "")
        loc = f" @ {e['location']}" if e.get("location") else ""
        lines.append(f"- {start}{loc}: {e.get('summary','No title')}")
    return "\n".join(lines)


def _gcal_free_time(date: str, duration_minutes: int = 60) -> str:
    svc = build("calendar", "v3", credentials=_gcal_creds())
    day_start = datetime.fromisoformat(date).replace(hour=8, minute=0, second=0, tzinfo=timezone.utc)
    day_end   = datetime.fromisoformat(date).replace(hour=22, minute=0, second=0, tzinfo=timezone.utc)
    result = svc.events().list(
        calendarId="primary", timeMin=day_start.isoformat(), timeMax=day_end.isoformat(),
        singleEvents=True, orderBy="startTime"
    ).execute()
    busy = []
    for e in result.get("items", []):
        s = e.get("start", {}).get("dateTime")
        en = e.get("end", {}).get("dateTime")
        if s and en:
            busy.append((datetime.fromisoformat(s.replace("Z","+00:00")),
                         datetime.fromisoformat(en.replace("Z","+00:00"))))
    busy.sort()
    free_slots, cursor = [], day_start
    for bs, be in busy:
        if (bs - cursor).total_seconds() >= duration_minutes * 60:
            free_slots.append(f"  {cursor.strftime('%I:%M %p')} - {bs.strftime('%I:%M %p')}")
        cursor = max(cursor, be)
    if (day_end - cursor).total_seconds() >= duration_minutes * 60:
        free_slots.append(f"  {cursor.strftime('%I:%M %p')} - {day_end.strftime('%I:%M %p')}")
    if not free_slots:
        return f"No free slots of {duration_minutes}+ min on {date}."
    return f"Free slots on {date}:\n" + "\n".join(free_slots)


def _canvas_courses() -> str:
    token = os.environ.get("CANVAS_TOKEN", "")
    if not token:
        return "CANVAS_TOKEN not set."
    with httpx.Client(timeout=10) as client:
        r = client.get("https://canvas.stanford.edu/api/v1/courses",
                       headers={"Authorization": f"Bearer {token}"},
                       params={"enrollment_state": "active"})
        courses = r.json()
    if not isinstance(courses, list):
        return "Could not fetch courses."
    return "\n".join([f"- {c.get('name','?')} (ID: {c.get('id')})" for c in courses])


def _course_deadlines(days_ahead: int = 30) -> str:
    HEADERS = {"User-Agent": "Mozilla/5.0"}
    now = datetime.now(timezone.utc)
    MONTH_MAP = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
                 "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
    all_deadlines = []

    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=15) as client:
        # CS231N
        r = client.get("https://cs231n.stanford.edu/schedule.html")
        soup = BeautifulSoup(r.text, "html.parser")
        for row in soup.find_all("tr"):
            cells = [td.get_text(separator=" ", strip=True) for td in row.find_all(["td","th"])]
            if len(cells) < 4: continue
            date_str, deadline_cell = cells[0], cells[-1]
            if re.search(r"(due|midterm|exam|poster|report|milestone)", deadline_cell, re.I):
                all_deadlines.append(("CS231N", date_str, deadline_cell))

        # CS224R
        r = client.get("https://cs224r.stanford.edu/")
        soup = BeautifulSoup(r.text, "html.parser")
        for row in soup.find_all("tr"):
            cells = [td.get_text(separator=" ", strip=True) for td in row.find_all(["td","th"])]
            if len(cells) < 3: continue
            week_date, deadline_cell = cells[0], cells[2]
            if re.search(r"(due|exam|poster|report|survey|proposal|milestone)", deadline_cell, re.I):
                m = re.search(r"(Mon|Tue|Wed|Thu|Fri)[,\s]+\w+ \d+", week_date)
                all_deadlines.append(("CS224R", m.group(0) if m else week_date[:25], deadline_cell))

    # Filter to days_ahead window
    upcoming = []
    for course, date_str, item in all_deadlines:
        m = re.search(r"(\w+)\s+(\d+)", date_str)
        if not m: continue
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if not month: continue
        try:
            dt = datetime(now.year, month, int(m.group(2)), 23, 59, tzinfo=timezone.utc)
            if 0 <= (dt - now).days <= days_ahead:
                upcoming.append((dt, course, item))
        except ValueError:
            continue

    if not upcoming:
        return f"No deadlines found in the next {days_ahead} days."
    upcoming.sort(key=lambda x: x[0])
    lines = [f"[{course}] {dt.strftime('%a %b %d')}: {item}" for dt, course, item in upcoming]
    return "\n".join(lines)


def _memory_search(query: str, n_results: int = 8) -> str:
    from query import get_context_for_agent
    return get_context_for_agent(query, n_results=n_results)


# ── Tool definitions for Claude ───────────────────────────────────────────────

TOOLS = [
    {
        "name": "search_memory",
        "description": (
            "Search long-term personal memory: 6 months of emails, calendar events, "
            "Canvas assignments, course content. Use for questions about past events, "
            "patterns, history, or anything that happened before today."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language search query"},
                "n_results": {"type": "integer", "description": "Number of results (default 8)", "default": 8},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_upcoming_events",
        "description": "Get live upcoming Google Calendar events for the next N days.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days_ahead": {"type": "integer", "description": "Days ahead to look (default 14)", "default": 14},
            },
        },
    },
    {
        "name": "get_course_deadlines",
        "description": "Get upcoming assignment deadlines scraped live from CS231N, CS224R, and CS153 course websites.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days_ahead": {"type": "integer", "description": "Days ahead to look (default 30)", "default": 30},
            },
        },
    },
    {
        "name": "search_emails",
        "description": (
            "Search Gmail in real time using Gmail search syntax. "
            "Examples: 'from:professor@stanford.edu', 'subject:CS231N', "
            "'from:amazon subject:order', 'is:unread'. "
            "Use for recent or specific emails not covered by memory search."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Gmail search query"},
                "max_results": {"type": "integer", "description": "Max results (default 10)", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "find_free_time",
        "description": "Find free time slots on a specific day in Google Calendar.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                "duration_minutes": {"type": "integer", "description": "Minimum slot length needed (default 60)", "default": 60},
            },
            "required": ["date"],
        },
    },
    {
        "name": "get_canvas_courses",
        "description": "Get current Canvas courses.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


# ── Tool execution ─────────────────────────────────────────────────────────────

def run_tool(name: str, inputs: dict) -> str:
    try:
        if name == "search_memory":
            return _memory_search(inputs["query"], inputs.get("n_results", 8))
        elif name == "get_upcoming_events":
            return _gcal_upcoming(inputs.get("days_ahead", 14))
        elif name == "get_course_deadlines":
            return _course_deadlines(inputs.get("days_ahead", 30))
        elif name == "search_emails":
            return _gmail_search(inputs["query"], inputs.get("max_results", 10))
        elif name == "find_free_time":
            return _gcal_free_time(inputs["date"], inputs.get("duration_minutes", 60))
        elif name == "get_canvas_courses":
            return _canvas_courses()
        else:
            return f"Unknown tool: {name}"
    except Exception as e:
        return f"Tool error ({name}): {e}"


# ── System prompt ─────────────────────────────────────────────────────────────

def build_system_prompt() -> str:
    from behavioral_profile import profile_as_system_prompt
    profile_str = profile_as_system_prompt()

    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%A, %B %d, %Y")

    return f"""You are a personal AI agent with deep knowledge of the user's digital life.
You have access to their emails, calendar, academic courses, and behavioral patterns.

Today's date: {today}

{profile_str}

Guidelines:
- Be specific and personal — you know this user's actual data, use it
- When answering questions about schedules, deadlines, or emails, always use the tools to get fresh data
- For questions about patterns or history, use search_memory first
- Cross-reference multiple sources when relevant (e.g. check both calendar and course deadlines for scheduling questions)
- Be concise but complete — the user wants answers, not explanations of what you're doing
- If you don't find something in memory, say so and suggest where it might be found
"""


# ── Agent loop ────────────────────────────────────────────────────────────────

def ask(question: str, history: list[dict] | None = None) -> tuple[str, list[dict]]:
    """
    Ask the agent a question. Returns (answer, updated_history).
    Pass history to maintain conversation context across turns.
    """
    client = anthropic.Anthropic()
    system = build_system_prompt()

    if history is None:
        history = []

    history.append({"role": "user", "content": question})
    messages = history.copy()

    while True:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=4096,
            system=system,
            tools=TOOLS,
            messages=messages,
        )

        # Collect assistant message
        assistant_content = response.content
        messages.append({"role": "assistant", "content": assistant_content})

        if response.stop_reason == "tool_use":
            # Execute all tool calls
            tool_results = []
            for block in assistant_content:
                if block.type == "tool_use":
                    console.print(f"  [dim]→ {block.name}({json.dumps(block.input)[:80]})[/dim]")
                    result = run_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result[:4000],  # cap tool output
                    })

            messages.append({"role": "user", "content": tool_results})

        else:
            # Final answer
            answer = ""
            for block in assistant_content:
                if hasattr(block, "text"):
                    answer += block.text

            # Update history with just the final exchange (not intermediate tool turns)
            history.append({"role": "assistant", "content": answer})
            return answer, history


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Personal Agent")
    parser.add_argument("question", nargs="?", help="Question to ask (omit for interactive mode)")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        console.print("[red]Error:[/red] ANTHROPIC_API_KEY not set.")
        console.print("Set it with: set ANTHROPIC_API_KEY=your_key_here")
        sys.exit(1)

    if args.question:
        # Single question mode
        console.print(f"\n[bold blue]Q:[/bold blue] {args.question}\n")
        answer, _ = ask(args.question)
        console.print(Markdown(answer))
    else:
        # Interactive chat mode
        console.print(Panel(
            "[bold blue]Personal Agent[/bold blue]\n"
            "Ask anything about your digital life.\n"
            "Type [bold]exit[/bold] or [bold]quit[/bold] to stop.",
            border_style="blue",
        ))

        history = []
        while True:
            try:
                question = input("\nYou: ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]Goodbye.[/dim]")
                break

            if not question:
                continue
            if question.lower() in ("exit", "quit", "q"):
                console.print("[dim]Goodbye.[/dim]")
                break

            console.print()
            answer, history = ask(question, history)
            console.print(Panel(Markdown(answer), border_style="green", title="Agent"))


if __name__ == "__main__":
    main()
