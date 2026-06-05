import httpx
import os
from mcp.server.fastmcp import FastMCP

CANVAS_TOKEN = os.environ["CANVAS_TOKEN"]
CANVAS_BASE = "https://canvas.stanford.edu/api/v1"
HEADERS = {"Authorization": f"Bearer {CANVAS_TOKEN}"}

mcp = FastMCP("canvas")

@mcp.tool()
async def get_todo_items() -> str:
    """Get all pending to-do items across all Canvas courses."""
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{CANVAS_BASE}/users/self/todo", headers=HEADERS)
        items = r.json()
    if not items:
        return "No to-do items found."
    lines = []
    for item in items:
        title = item.get("assignment", {}).get("name", "Unknown")
        due = item.get("assignment", {}).get("due_at", "No due date")
        course = item.get("context_name", "Unknown course")
        lines.append(f"- [{course}] {title} — due {due}")
    return "\n".join(lines)

@mcp.tool()
async def get_upcoming_assignments(days_ahead: int = 7) -> str:
    """Get assignments due in the next N days."""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{CANVAS_BASE}/calendar_events",
            headers=HEADERS,
            params={"type": "assignment", "per_page": 50}
        )
        events = r.json()
    if not events:
        return "No upcoming assignments."
    lines = [f"- {e.get('title', 'Unknown')} — {e.get('end_at', 'No date')}" for e in events]
    return "\n".join(lines)

@mcp.tool()
async def get_courses() -> str:
    """List all active Canvas courses."""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{CANVAS_BASE}/courses",
            headers=HEADERS,
            params={"enrollment_state": "active"}
        )
        courses = r.json()
    return "\n".join([f"- {c.get('name', 'Unknown')} (ID: {c.get('id')})" for c in courses])

if __name__ == "__main__":
    mcp.run(transport="stdio")
