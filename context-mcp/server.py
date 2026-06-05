"""
PersonalContext MCP Server

The memory system for AI agents — exposed as MCP tools.

Tools:
    context_get(task)              → full PersonalContext for a task
    context_schedule()             → calendar + free blocks
    context_energy_profile()       → work style, peak hours, confidence
    context_preferences(domain)    → preferences by domain
    context_deadlines()            → upcoming deadlines by urgency
    context_memory(query)          → semantic search over personal data
"""

from mcp.server.fastmcp import FastMCP
from context_engine import context, get_user_profile, search_memory, explain_response

mcp = FastMCP("personal-context")


@mcp.tool()
def context_get(task: str) -> dict:
    """
    Full PersonalContext for a task — the main entry point.

    Returns a three-layer object:
      structured  → deadlines, calendar free blocks
      behavioral  → work style, peak hours (with confidence score)
      semantic    → relevant memories, identity tags

    Call this before any task that benefits from knowing the user's
    schedule, history, preferences, or active commitments.

    Args:
        task: Natural language description of what the agent is doing.
              e.g. "find study time for CS231N this week"
              e.g. "draft email to professor about deadline extension"
    """
    return context.get(task)


@mcp.tool()
def context_schedule(days: int = 14) -> dict:
    """
    Calendar context: upcoming events and free time during peak focus hours.

    Args:
        days: How many days ahead to look (default 14)
    """
    return context.schedule(days)


@mcp.tool()
def context_energy_profile() -> dict:
    """
    Behavioral energy profile with confidence score.

    Returns work style, peak focus hours, busiest days, and
    a confidence score based on how much data backs the inference.
    """
    return context.energy_profile()


@mcp.tool()
def context_preferences(domain: str = None) -> dict:
    """
    User preferences, optionally filtered by domain.

    Args:
        domain: Optional filter — one of: study, communication, scheduling
                Omit for all preferences.
    """
    return context.preferences(domain)


@mcp.tool()
def context_deadlines(days: int = 30) -> list:
    """
    Upcoming deadlines sorted by urgency (high → low).

    Args:
        days: Lookahead window in days (default 30)
    """
    return context.deadlines(days)


@mcp.tool()
def context_memory(query: str, source: str = None) -> list:
    """
    Semantic search over personal data.

    Lower-level tool for direct memory lookup. Prefer context_get()
    for most tasks — use this for targeted retrieval.

    Args:
        query:  Natural language search string
        source: Optional filter — gmail | gcal | canvas | course_websites | purchases
    """
    return context.memory(query, source)


@mcp.tool()
def context_explain(task: str, response: str, ctx: dict) -> dict:
    """
    Trace which retrieved context drove which claims in an agent response.

    Returns per-claim source attribution, confidence scores,
    and an overall personalization score.

    Args:
        task:     The original task given to the agent
        response: The agent's response text
        ctx:      The PersonalContext object that was used (from context_get)
    """
    return explain_response(task, response, ctx)


if __name__ == "__main__":
    mcp.run()
