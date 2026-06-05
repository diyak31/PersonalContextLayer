"""
Behavioral profile extractor — analyzes raw data to build a structured
JSON profile of the user's patterns, preferences, and behavior.

Usage:
    python profile.py           # generate profile.json
    python profile.py --show    # print current profile
"""

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.pretty import pprint

console = Console()

AGENT_DIR    = Path(__file__).parent
RAW_DIR      = AGENT_DIR / "data" / "raw"
PROFILE_PATH = AGENT_DIR / "data" / "profile.json"


def _load(source: str) -> list[dict]:
    path = RAW_DIR / f"{source}.jsonl"
    if not path.exists():
        return []
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                records.append(json.loads(line))
            except Exception:
                continue
    return records


def _parse_dt(s: str) -> datetime | None:
    if not s:
        return None
    for fmt in [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d",
    ]:
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    return None


# ── Analyzers ─────────────────────────────────────────────────────────────────

def analyze_gmail(records: list[dict]) -> dict:
    sent     = [r for r in records if r.get("label") == "sent"]
    inbox    = [r for r in records if r.get("label") == "inbox"]

    # Hour-of-day distribution for sent emails
    send_hours = Counter()
    for r in sent:
        dt = _parse_dt(r.get("date", ""))
        if dt:
            send_hours[dt.hour] += 1

    # Top contacts (who you email most)
    to_counter = Counter()
    for r in sent:
        to_field = r.get("to", "")
        emails = re.findall(r"[\w.+-]+@[\w-]+\.[a-z]+", to_field.lower())
        for e in emails:
            to_counter[e] += 1

    # Top senders (who emails you most)
    from_counter = Counter()
    for r in inbox:
        from_field = r.get("from", "")
        emails = re.findall(r"[\w.+-]+@[\w-]+\.[a-z]+", from_field.lower())
        for e in emails:
            from_counter[e] += 1

    # Peak email hours
    peak_hours = [h for h, _ in send_hours.most_common(3)]

    return {
        "total_sent": len(sent),
        "total_inbox": len(inbox),
        "peak_send_hours": peak_hours,
        "top_contacts_emailed": [e for e, _ in to_counter.most_common(10)],
        "top_senders": [e for e, _ in from_counter.most_common(10)],
        "send_hour_distribution": dict(sorted(send_hours.items())),
    }


def analyze_gcal(records: list[dict]) -> dict:
    now = datetime.now(timezone.utc)

    # Duration distribution
    durations = []
    hour_distribution = Counter()
    day_distribution  = Counter()
    calendars_used    = Counter()
    locations         = Counter()

    for r in records:
        start_str = r.get("start", "")
        end_str   = r.get("end", "")
        dt_start  = _parse_dt(start_str)
        dt_end    = _parse_dt(end_str)

        if dt_start and dt_end:
            duration_min = (dt_end - dt_start).total_seconds() / 60
            if 0 < duration_min < 480:  # ignore all-day or weird events
                durations.append(duration_min)

        if dt_start:
            hour_distribution[dt_start.hour] += 1
            day_distribution[dt_start.strftime("%A")] += 1

        cal = r.get("calendar", "")
        if cal:
            calendars_used[cal] += 1

        loc = r.get("location", "")
        if loc:
            locations[loc] += 1

    avg_duration = round(sum(durations) / len(durations), 1) if durations else 0
    peak_hours   = [h for h, _ in hour_distribution.most_common(3)]
    busiest_days = [d for d, _ in day_distribution.most_common(3)]

    return {
        "total_events": len(records),
        "avg_event_duration_minutes": avg_duration,
        "peak_scheduling_hours": peak_hours,
        "busiest_days": busiest_days,
        "calendars": dict(calendars_used.most_common()),
        "frequent_locations": [loc for loc, _ in locations.most_common(5)],
    }


def analyze_purchases(records: list[dict]) -> dict:
    merchant_counter = Counter()
    amounts = []

    for r in records:
        merchant = r.get("merchant", "Unknown")
        merchant_counter[merchant] += 1

        amount_str = r.get("amount", "")
        if amount_str:
            try:
                amount = float(amount_str.replace("$", "").replace(",", ""))
                amounts.append(amount)
            except ValueError:
                pass

    return {
        "total_purchases": len(records),
        "top_merchants": dict(merchant_counter.most_common(10)),
        "avg_purchase_amount": round(sum(amounts) / len(amounts), 2) if amounts else 0,
        "total_spend_tracked": round(sum(amounts), 2),
    }


def analyze_academics(canvas: list[dict], courses: list[dict]) -> dict:
    course_names = [r["name"] for r in canvas if r.get("type") == "course"]
    assignments  = [r for r in canvas if r.get("type") == "assignment"]

    return {
        "current_courses": course_names,
        "total_assignments_tracked": len(assignments),
        "course_websites": ["cs231n.stanford.edu", "cs224r.stanford.edu", "cs153.stanford.edu"],
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def build_profile() -> dict:
    console.print("\n[bold blue]Building behavioral profile...[/bold blue]\n")

    gmail_records    = _load("gmail")
    gcal_records     = _load("gcal")
    canvas_records   = _load("canvas")
    purchase_records = _load("purchases")
    course_records   = _load("course_websites")

    profile = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "email": analyze_gmail(gmail_records) if gmail_records else {},
        "calendar": analyze_gcal(gcal_records) if gcal_records else {},
        "purchases": analyze_purchases(purchase_records) if purchase_records else {},
        "academics": analyze_academics(canvas_records, course_records),
    }

    # Synthesize top-level behavioral summary
    email_data    = profile["email"]
    calendar_data = profile["calendar"]

    peak_hours = email_data.get("peak_send_hours", [])
    time_label = "night owl" if any(h >= 22 or h <= 4 for h in peak_hours) else \
                 "evening person" if any(18 <= h < 22 for h in peak_hours) else \
                 "morning person"

    profile["summary"] = {
        "work_style": time_label,
        "peak_activity_hours": peak_hours,
        "busiest_calendar_days": calendar_data.get("busiest_days", []),
        "avg_meeting_duration_minutes": calendar_data.get("avg_event_duration_minutes", 0),
        "top_email_contacts": email_data.get("top_contacts_emailed", [])[:5],
        "current_courses": profile["academics"]["current_courses"],
        "top_merchants": list(profile["purchases"].get("top_merchants", {}).keys())[:5],
    }

    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)

    console.print(f"[green]✓[/green] Profile saved to {PROFILE_PATH}")
    return profile


def load_profile() -> dict:
    """Load the profile for use in agent system prompt."""
    if not PROFILE_PATH.exists():
        return {}
    with open(PROFILE_PATH, encoding="utf-8") as f:
        return json.load(f)


def profile_as_system_prompt() -> str:
    """Return profile as a concise system prompt snippet for the agent."""
    p = load_profile()
    if not p:
        return ""

    summary = p.get("summary", {})
    lines = [
        "About the user:",
        f"- Work style: {summary.get('work_style', 'unknown')}",
        f"- Most active hours: {summary.get('peak_activity_hours', [])}",
        f"- Busiest calendar days: {summary.get('busiest_calendar_days', [])}",
        f"- Avg meeting duration: {summary.get('avg_meeting_duration_minutes')} min",
        f"- Top email contacts: {', '.join(summary.get('top_email_contacts', [])[:3])}",
        f"- Current courses: {', '.join(summary.get('current_courses', []))}",
        f"- Frequent purchases: {', '.join(summary.get('top_merchants', []))}",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--show", action="store_true", help="Print existing profile")
    args = parser.parse_args()

    if args.show:
        profile = load_profile()
        if profile:
            pprint(profile)
        else:
            console.print("[yellow]No profile yet. Run without --show to generate.[/yellow]")
        return

    profile = build_profile()
    console.print("\n[bold]Summary:[/bold]")
    pprint(profile["summary"])


if __name__ == "__main__":
    main()
