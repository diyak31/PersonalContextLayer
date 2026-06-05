import re
from datetime import datetime, timezone
from mcp.server.fastmcp import FastMCP
import httpx
from bs4 import BeautifulSoup

mcp = FastMCP("course-websites")

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

COURSES = {
    "cs231n": {
        "name": "Deep Learning for Computer Vision",
        "url": "https://cs231n.stanford.edu",
        "schedule_path": "/schedule.html",
        "assignments_path": "/assignments.html",
    },
    "cs224r": {
        "name": "Deep Reinforcement Learning",
        "url": "https://cs224r.stanford.edu",
        "schedule_path": "/",
        "assignments_path": "/",
    },
    "cs153": {
        "name": "Frontier Systems",
        "url": "https://cs153.stanford.edu",
        "schedule_path": "/",
        "assignments_path": "/",
    },
}


def _get(url: str) -> BeautifulSoup:
    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=15) as client:
        r = client.get(url)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")


def _scrape_cs231n_deadlines() -> list[dict]:
    soup = _get("https://cs231n.stanford.edu/schedule.html")
    deadlines = []
    for row in soup.find_all("tr"):
        cells = [td.get_text(separator=" ", strip=True) for td in row.find_all(["td", "th"])]
        if len(cells) < 2:
            continue
        date_str = cells[0].strip()
        deadline_cell = cells[-1] if len(cells) >= 4 else ""
        event_cell = cells[-2] if len(cells) >= 4 else ""

        if deadline_cell and re.search(r"(due|out|midterm|exam|poster|report)", deadline_cell, re.I):
            deadlines.append({"date": date_str, "item": deadline_cell, "course": "CS231N"})
        if event_cell and re.search(r"(due|out|midterm|exam|poster|report)", event_cell, re.I):
            deadlines.append({"date": date_str, "item": event_cell, "course": "CS231N"})
    return deadlines


def _scrape_cs224r_deadlines() -> list[dict]:
    soup = _get("https://cs224r.stanford.edu/")
    deadlines = []
    for row in soup.find_all("tr"):
        cells = [td.get_text(separator=" ", strip=True) for td in row.find_all(["td", "th"])]
        if len(cells) < 3:
            continue
        # Format: "Week N  Date" | "Lecture Topic" | "Due/Out Items" | reading
        week_date = cells[0].strip()
        deadline_cell = cells[2] if len(cells) > 2 else ""
        if deadline_cell and re.search(r"(due|out|exam|poster|report|survey|proposal|milestone)", deadline_cell, re.I):
            # Extract just the date portion (e.g. "Fri, April 10")
            date_match = re.search(r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun)[,\s]+\w+ \d+", week_date)
            date_str = date_match.group(0) if date_match else week_date[:30]
            deadlines.append({"date": date_str, "item": deadline_cell, "course": "CS224R"})
    return deadlines


def _scrape_cs153_info() -> list[dict]:
    # CS153 has no homework — graded on attendance (65%) and project (35%)
    # Speaker dates are not published until day-of
    return [
        {"date": "Weekly", "item": "Attendance (Tue/Thu 12:00-1:20pm, Hewlett 200) — 65% of grade", "course": "CS153"},
        {"date": "Jun 3", "item": "Project: The One-Person Frontier Lab — due end of quarter (35% of grade)", "course": "CS153"},
    ]


@mcp.tool()
def get_all_deadlines() -> str:
    """
    Get all upcoming assignment deadlines across CS231N, CS224R, and CS153
    scraped live from the course websites.
    """
    all_deadlines = []
    all_deadlines += _scrape_cs231n_deadlines()
    all_deadlines += _scrape_cs224r_deadlines()
    all_deadlines += _scrape_cs153_info()

    if not all_deadlines:
        return "No deadlines found."

    # Group by course
    by_course: dict[str, list] = {}
    for d in all_deadlines:
        by_course.setdefault(d["course"], []).append(d)

    lines = []
    for course, items in by_course.items():
        lines.append(f"\n=== {course} ===")
        for item in items:
            lines.append(f"  {item['date']}: {item['item']}")

    return "\n".join(lines)


@mcp.tool()
def get_cs231n_schedule() -> str:
    """Get the full CS231N schedule including all deadlines and events."""
    soup = _get("https://cs231n.stanford.edu/schedule.html")
    rows = soup.find_all("tr")
    lines = []
    for row in rows:
        cells = [td.get_text(separator=" ", strip=True) for td in row.find_all(["td", "th"])]
        if cells and any(c.strip() for c in cells):
            lines.append(" | ".join(c for c in cells if c.strip()))
    return "\n".join(lines)


@mcp.tool()
def get_cs224r_schedule() -> str:
    """Get the full CS224R schedule including all deadlines and events."""
    soup = _get("https://cs224r.stanford.edu/")
    rows = soup.find_all("tr")
    lines = []
    for row in rows:
        cells = [td.get_text(separator=" ", strip=True) for td in row.find_all(["td", "th"])]
        if cells and any(c.strip() for c in cells):
            lines.append(" | ".join(c for c in cells if c.strip())[:200])
    return "\n".join(lines)


@mcp.tool()
def get_cs231n_assignments() -> str:
    """Get CS231N assignment descriptions and deadlines."""
    soup = _get("https://cs231n.stanford.edu/assignments.html")
    return soup.get_text(separator="\n", strip=True)


@mcp.tool()
def get_upcoming_deadlines(days_ahead: int = 14) -> str:
    """
    Get deadlines coming up in the next N days (default 14) across all courses.
    Parses dates from course websites and filters to the upcoming window.
    """
    all_deadlines = _scrape_cs231n_deadlines() + _scrape_cs224r_deadlines()
    now = datetime.now(timezone.utc)
    upcoming = []

    MONTH_MAP = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }

    for d in all_deadlines:
        raw = d["date"]
        # Try to parse dates like "Apr 16", "Fri, April 10", "May 7"
        m = re.search(r"(\w+)\s+(\d+)", raw)
        if not m:
            continue
        month_str, day_str = m.group(1).lower()[:3], int(m.group(2))
        month = MONTH_MAP.get(month_str)
        if not month:
            continue
        year = now.year
        try:
            dt = datetime(year, month, day_str, 23, 59, tzinfo=timezone.utc)
            delta = (dt - now).days
            if 0 <= delta <= days_ahead:
                upcoming.append((dt, d["course"], d["item"]))
        except ValueError:
            continue

    if not upcoming:
        return f"No deadlines in the next {days_ahead} days."

    upcoming.sort(key=lambda x: x[0])
    lines = [f"Deadlines in the next {days_ahead} days:\n"]
    for dt, course, item in upcoming:
        lines.append(f"  [{course}] {dt.strftime('%a %b %d')}: {item}")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="stdio")
