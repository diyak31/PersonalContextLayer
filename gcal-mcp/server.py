from datetime import datetime, timezone, timedelta
from mcp.server.fastmcp import FastMCP
from googleapiclient.discovery import build
from auth import get_credentials

mcp = FastMCP("gcal")


def _get_service():
    return build("calendar", "v3", credentials=get_credentials())


def _fmt(dt_str: str) -> str:
    """Format an ISO datetime string to a readable local form."""
    if not dt_str:
        return "No date"
    # All-day events have date only (no time component)
    if "T" not in dt_str:
        return dt_str
    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    return dt.strftime("%a %b %d, %Y %I:%M %p %Z")


def _now_and_future(days: int):
    now = datetime.now(timezone.utc)
    future = now + timedelta(days=days)
    return now.isoformat(), future.isoformat()


@mcp.tool()
def get_upcoming_events(days_ahead: int = 7, max_results: int = 20) -> str:
    """
    Get upcoming calendar events for the next N days (default 7).
    Returns event name, date/time, location, and description.
    """
    service = _get_service()
    time_min, time_max = _now_and_future(days_ahead)

    result = service.events().list(
        calendarId="primary",
        timeMin=time_min,
        timeMax=time_max,
        maxResults=max_results,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = result.get("items", [])
    if not events:
        return f"No events in the next {days_ahead} days."

    lines = []
    for e in events:
        start = e.get("start", {})
        dt = start.get("dateTime") or start.get("date", "")
        location = e.get("location", "")
        loc_str = f" @ {location}" if location else ""
        lines.append(f"- {_fmt(dt)}{loc_str}\n  {e.get('summary', 'No title')}")
        if e.get("description"):
            lines[-1] += f"\n  {e['description'][:100]}"
    return "\n\n".join(lines)


@mcp.tool()
def get_events_on_date(date: str) -> str:
    """
    Get all events on a specific date.
    Args:
        date: date string in YYYY-MM-DD format (e.g. "2026-04-20")
    """
    service = _get_service()
    day_start = datetime.fromisoformat(date).replace(
        hour=0, minute=0, second=0, tzinfo=timezone.utc
    )
    day_end = day_start + timedelta(days=1)

    result = service.events().list(
        calendarId="primary",
        timeMin=day_start.isoformat(),
        timeMax=day_end.isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = result.get("items", [])
    if not events:
        return f"No events on {date}."

    lines = []
    for e in events:
        start = e.get("start", {})
        dt = start.get("dateTime") or start.get("date", "")
        lines.append(f"- {_fmt(dt)}: {e.get('summary', 'No title')}")
    return "\n".join(lines)


@mcp.tool()
def find_free_time(date: str, duration_minutes: int = 60) -> str:
    """
    Find free time slots on a given day (between 8am and 10pm).
    Args:
        date: date string in YYYY-MM-DD format (e.g. "2026-04-20")
        duration_minutes: minimum slot length needed (default 60 min)
    """
    service = _get_service()
    day_start = datetime.fromisoformat(date).replace(
        hour=8, minute=0, second=0, tzinfo=timezone.utc
    )
    day_end = datetime.fromisoformat(date).replace(
        hour=22, minute=0, second=0, tzinfo=timezone.utc
    )

    result = service.events().list(
        calendarId="primary",
        timeMin=day_start.isoformat(),
        timeMax=day_end.isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = result.get("items", [])

    # Build busy blocks
    busy = []
    for e in events:
        s = e.get("start", {}).get("dateTime")
        en = e.get("end", {}).get("dateTime")
        if s and en:
            busy.append((
                datetime.fromisoformat(s.replace("Z", "+00:00")),
                datetime.fromisoformat(en.replace("Z", "+00:00")),
            ))
    busy.sort()

    # Find gaps
    free_slots = []
    cursor = day_start
    for bs, be in busy:
        if (bs - cursor).total_seconds() >= duration_minutes * 60:
            free_slots.append(f"  {cursor.strftime('%I:%M %p')} – {bs.strftime('%I:%M %p')}")
        cursor = max(cursor, be)
    if (day_end - cursor).total_seconds() >= duration_minutes * 60:
        free_slots.append(f"  {cursor.strftime('%I:%M %p')} – {day_end.strftime('%I:%M %p')}")

    if not free_slots:
        return f"No free slots of {duration_minutes}+ minutes found on {date}."
    return f"Free slots on {date} ({duration_minutes}+ min):\n" + "\n".join(free_slots)


@mcp.tool()
def create_event(
    title: str,
    date: str,
    start_time: str,
    end_time: str,
    description: str = "",
    location: str = "",
) -> str:
    """
    Create a new calendar event.
    Args:
        title: event title
        date: date in YYYY-MM-DD format (e.g. "2026-04-20")
        start_time: start time in HH:MM 24h format (e.g. "14:00")
        end_time: end time in HH:MM 24h format (e.g. "15:00")
        description: optional event description
        location: optional location
    """
    service = _get_service()

    start_dt = f"{date}T{start_time}:00"
    end_dt = f"{date}T{end_time}:00"

    event_body = {
        "summary": title,
        "start": {"dateTime": start_dt, "timeZone": "America/Los_Angeles"},
        "end": {"dateTime": end_dt, "timeZone": "America/Los_Angeles"},
    }
    if description:
        event_body["description"] = description
    if location:
        event_body["location"] = location

    event = service.events().insert(calendarId="primary", body=event_body).execute()
    return f"Event created: {event.get('summary')}\nLink: {event.get('htmlLink')}"


@mcp.tool()
def list_calendars() -> str:
    """List all calendars in your Google account."""
    service = _get_service()
    result = service.calendarList().list().execute()
    calendars = result.get("items", [])
    lines = [
        f"- {c.get('summary')} (ID: {c.get('id')}, primary: {c.get('primary', False)})"
        for c in calendars
    ]
    return "\n".join(lines) if lines else "No calendars found."


@mcp.tool()
def get_this_week() -> str:
    """Get all events for the current week (Mon–Sun)."""
    today = datetime.now(timezone.utc)
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    days = (sunday - today).days + 1
    return get_upcoming_events(days_ahead=days, max_results=50)


if __name__ == "__main__":
    mcp.run(transport="stdio")
