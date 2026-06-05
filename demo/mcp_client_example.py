"""
PersonalContext MCP — integration example.

Shows how to call the context layer from any agent in ~15 lines.
No knowledge of the underlying data sources required.

Run:
    python demo/mcp_client_example.py
    python demo/mcp_client_example.py --task "plan my week"
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / "agent" / ".env")

SERVER_SCRIPT = str(Path(__file__).parent.parent / "context-mcp" / "server.py")
PYTHON        = str(Path(__file__).parent.parent / "agent" / ".venv" / "Scripts" / "python.exe")


# ── Step 1: connect to the PersonalContext MCP server ─────────────────────────

async def get_personal_context(task: str) -> dict:
    """One call to get all personal context for a task."""
    server_params = StdioServerParameters(
        command=PYTHON,
        args=[SERVER_SCRIPT],
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "get_personal_context",
                {"task": task},
            )
            return json.loads(result.content[0].text)


# ── Step 2: build any agent on top of it ──────────────────────────────────────

async def run_agent(task: str):
    print(f"\nTask: {task}\n")

    print("Fetching personal context...")
    context = await get_personal_context(task)
    print(f"  Retrieved {len(context.get('relevant_memories', []))} memories, "
          f"{len(context.get('deadlines', []))} deadlines\n")

    # Any agent — LangChain, LlamaIndex, custom — can use this context
    client = Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        system=f"""You are a helpful personal assistant.
Personal context: {json.dumps(context, indent=2)}
Answer directly using this context. Be specific.""",
        messages=[{"role": "user", "content": task}],
    )

    print("Response:")
    print(response.content[0].text)
    return response.content[0].text


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PersonalContext MCP client example")
    parser.add_argument(
        "--task",
        default="Find me a 2-hour study block for CS231N this week",
        help="Task to run",
    )
    args = parser.parse_args()
    asyncio.run(run_agent(args.task))
