"""
Ingestion pipeline — pulls raw data from all personal data sources
and saves to data/raw/ as JSONL files.

Usage:
    python ingest.py                  # ingest everything
    python ingest.py --source gmail   # ingest one source
    python ingest.py --since 90       # last N days (default 180)
"""

import argparse
import base64
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from rich.console import Console
from rich.progress import track

console = Console()
RAW_DIR = Path(__file__).parent / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

AGENT_DIR = Path(__file__).parent
GMAIL_TOKEN = AGENT_DIR.parent / "gmail-mcp" / "token.json"
GCAL_TOKEN  = AGENT_DIR.parent / "gcal-mcp"  / "token.json"

CANVAS_TOKEN = os.environ.get("CANVAS_TOKEN", "")
CANVAS_BASE  = "https://canvas.stanford.edu/api/v1"


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _gmail_service():
    scopes = ["https://www.googleapis.com/auth/gmail.readonly"]
    creds = Credentials.from_authorized_user_file(str(GMAIL_TOKEN), scopes)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("gmail", "v1", credentials=creds)


def _gcal_service():
    scopes = ["https://www.googleapis.com/auth/calendar.readonly"]
    creds = Credentials.from_authorized_user_file(str(GCAL_TOKEN), scopes)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("calendar", "v3", credentials=creds)


# ── Writers ───────────────────────────────────────────────────────────────────

def _write(source: str, records: list[dict]):
    path = RAW_DIR / f"{source}.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    console.print(f"  [green]OK[/green] {source}: {len(records)} records -> {path.name}")


# ── Gmail ─────────────────────────────────────────────────────────────────────

def _decode_body(payload: dict) -> str:
    mime = payload.get("mimeType", "")
    if mime == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    if mime.startswith("multipart/"):
        for part in payload.get("parts", []):
            text = _decode_body(part)
            if text:
                return text
    return ""


def _header(headers: list, name: str) -> str:
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def ingest_gmail(since_days: int = 180):
    console.print("\n[bold]Gmail[/bold]")
    svc = _gmail_service()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%Y/%m/%d")
    records = []

    for label, query in [
        ("inbox",  f"in:inbox after:{cutoff}"),
        ("sent",   f"in:sent after:{cutoff}"),
        ("receipts", f"after:{cutoff} (subject:receipt OR subject:order OR subject:invoice OR subject:confirmation OR from:amazon OR from:doordash OR from:uber OR from:instacart OR from:venmo OR from:paypal)"),
    ]:
        page_token = None
        count = 0
        while True:
            params = {"userId": "me", "q": query, "maxResults": 500}
            if page_token:
                params["pageToken"] = page_token
            result = svc.users().messages().list(**params).execute()
            msgs = result.get("messages", [])
            if not msgs:
                break

            for msg in track(msgs, description=f"  {label}...", console=console):
                try:
                    m = svc.users().messages().get(
                        userId="me", id=msg["id"], format="full"
                    ).execute()
                    headers = m.get("payload", {}).get("headers", [])
                    body = _decode_body(m.get("payload", {}))
                    date_str = _header(headers, "Date")

                    records.append({
                        "id": m["id"],
                        "source": "gmail",
                        "label": label,
                        "from": _header(headers, "From"),
                        "to": _header(headers, "To"),
                        "subject": _header(headers, "Subject"),
                        "date": date_str,
                        "snippet": m.get("snippet", ""),
                        "body": body[:3000],  # cap body length
                        "thread_id": m.get("threadId", ""),
                    })
                    count += 1
                except Exception:
                    continue

            page_token = result.get("nextPageToken")
            if not page_token or count >= 2000:
                break

    _write("gmail", records)


# ── Google Calendar ───────────────────────────────────────────────────────────

def ingest_gcal(since_days: int = 365):
    console.print("\n[bold]Google Calendar[/bold]")
    svc = _gcal_service()
    now = datetime.now(timezone.utc)
    time_min = (now - timedelta(days=since_days)).isoformat()
    time_max = (now + timedelta(days=180)).isoformat()  # include future events too

    # Get all calendars
    cal_list = svc.calendarList().list().execute().get("items", [])
    records = []

    for cal in cal_list:
        cal_id   = cal["id"]
        cal_name = cal.get("summary", cal_id)
        try:
            result = svc.events().list(
                calendarId=cal_id,
                timeMin=time_min,
                timeMax=time_max,
                maxResults=2500,
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            for e in result.get("items", []):
                start = e.get("start", {})
                end   = e.get("end",   {})
                attendees = [a.get("email", "") for a in e.get("attendees", [])]
                records.append({
                    "id": e["id"],
                    "source": "gcal",
                    "calendar": cal_name,
                    "title": e.get("summary", ""),
                    "description": (e.get("description") or "")[:500],
                    "location": e.get("location", ""),
                    "start": start.get("dateTime") or start.get("date", ""),
                    "end": end.get("dateTime") or end.get("date", ""),
                    "attendees": attendees,
                    "status": e.get("status", ""),
                    "recurring": bool(e.get("recurringEventId")),
                })
        except Exception:
            continue

    _write("gcal", records)


# ── Canvas ────────────────────────────────────────────────────────────────────

def ingest_canvas():
    console.print("\n[bold]Canvas[/bold]")
    if not CANVAS_TOKEN:
        console.print("  [yellow]⚠[/yellow] CANVAS_TOKEN not set, skipping")
        return

    headers = {"Authorization": f"Bearer {CANVAS_TOKEN}"}
    records = []

    with httpx.Client(timeout=15) as client:
        # Courses
        r = client.get(f"{CANVAS_BASE}/courses", headers=headers,
                       params={"enrollment_state": "active", "per_page": 50})
        courses = r.json() if isinstance(r.json(), list) else []

        for course in courses:
            cid   = course.get("id")
            cname = course.get("name", "Unknown")
            records.append({
                "id": f"course_{cid}",
                "source": "canvas",
                "type": "course",
                "name": cname,
                "course_id": cid,
            })

            # Assignments
            r2 = client.get(f"{CANVAS_BASE}/courses/{cid}/assignments",
                            headers=headers, params={"per_page": 100})
            assignments = r2.json() if isinstance(r2.json(), list) else []
            for a in assignments:
                records.append({
                    "id": f"assignment_{a.get('id')}",
                    "source": "canvas",
                    "type": "assignment",
                    "course": cname,
                    "name": a.get("name", ""),
                    "due_at": a.get("due_at", ""),
                    "points_possible": a.get("points_possible"),
                    "description": BeautifulSoup(
                        a.get("description") or "", "html.parser"
                    ).get_text()[:500],
                })

    _write("canvas", records)


# ── Course Websites ───────────────────────────────────────────────────────────

def ingest_course_websites():
    console.print("\n[bold]Course Websites[/bold]")
    HEADERS = {"User-Agent": "Mozilla/5.0"}
    records = []

    PAGES = [
        ("cs231n", "Deep Learning for CV",     "https://cs231n.stanford.edu/schedule.html"),
        ("cs231n", "Deep Learning for CV",     "https://cs231n.stanford.edu/assignments.html"),
        ("cs224r", "Deep Reinforcement Learning", "https://cs224r.stanford.edu/"),
        ("cs153",  "Frontier Systems",         "https://cs153.stanford.edu/"),
    ]

    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=15) as client:
        for course_id, course_name, url in PAGES:
            try:
                r = client.get(url)
                soup = BeautifulSoup(r.text, "html.parser")
                text = soup.get_text(separator="\n", strip=True)
                records.append({
                    "id": f"{course_id}_{url.split('/')[-1] or 'home'}",
                    "source": "course_websites",
                    "course": course_id,
                    "course_name": course_name,
                    "url": url,
                    "content": text[:8000],
                })
            except Exception as e:
                console.print(f"  [yellow]⚠[/yellow] Failed {url}: {e}")

    _write("course_websites", records)


# ── Purchase extraction from Gmail receipts ───────────────────────────────────

def extract_purchases():
    """Post-process Gmail receipts JSONL into a structured purchases file."""
    gmail_path = RAW_DIR / "gmail.jsonl"
    if not gmail_path.exists():
        return

    purchases = []
    with open(gmail_path, encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if rec.get("label") != "receipts":
                continue

            subject = rec.get("subject", "").lower()
            sender  = rec.get("from", "").lower()
            snippet = rec.get("snippet", "")

            # Extract merchant
            merchant = "Unknown"
            for m in ["amazon", "doordash", "uber", "instacart", "venmo",
                      "paypal", "apple", "google", "netflix", "spotify",
                      "airbnb", "delta", "united", "southwest"]:
                if m in sender or m in subject:
                    merchant = m.capitalize()
                    break

            # Extract amount
            amount_match = re.search(r"\$[\d,]+\.?\d*", snippet + rec.get("body", ""))
            amount = amount_match.group(0) if amount_match else None

            purchases.append({
                "id": rec["id"],
                "source": "gmail_purchases",
                "merchant": merchant,
                "subject": rec.get("subject", ""),
                "amount": amount,
                "date": rec.get("date", ""),
                "snippet": snippet[:200],
            })

    _write("purchases", purchases)
    console.print(f"  [dim]Extracted {len(purchases)} purchase records from Gmail[/dim]")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Ingest personal data")
    parser.add_argument("--source", choices=["gmail", "gcal", "canvas", "courses", "all"],
                        default="all")
    parser.add_argument("--since", type=int, default=180,
                        help="Days of history to pull (default 180)")
    args = parser.parse_args()

    console.print(f"\n[bold blue]Personal Agent — Data Ingestion[/bold blue]")
    console.print(f"Source: [cyan]{args.source}[/cyan]  |  History: [cyan]{args.since} days[/cyan]\n")

    if args.source in ("gmail", "all"):
        ingest_gmail(since_days=args.since)
        extract_purchases()
    if args.source in ("gcal", "all"):
        ingest_gcal(since_days=args.since)
    if args.source in ("canvas", "all"):
        ingest_canvas()
    if args.source in ("courses", "all"):
        ingest_course_websites()

    console.print("\n[bold green]✓ Ingestion complete.[/bold green]")
    console.print("Next: run [cyan]python embed.py[/cyan] to build the vector database.\n")


if __name__ == "__main__":
    main()
