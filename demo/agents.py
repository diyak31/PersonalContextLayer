"""
Agent implementations for every supported platform.

Each platform has a naive variant (no context) and an enhanced variant
(PersonalContext layer plugged in). Both take a task string; enhanced
variants also return the context dict for display.

Supported platforms:
  langchain   — LangChain + LangGraph ReAct agent
  crewai      — CrewAI agent with BaseTool
  llamaindex  — LlamaIndex ReActAgent with FunctionTool
  mcp         — Raw MCP client calling our context server
  custom      — Direct Anthropic SDK (reference implementation)
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / "agent" / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent / "context-mcp"))
from context_engine import get_context, explain_response

client = Anthropic()
MODEL  = "claude-sonnet-4-6"

CONTEXT_SERVER = str(Path(__file__).parent.parent / "context-mcp" / "server.py")
PYTHON         = str(Path(__file__).parent.parent / "agent" / ".venv" / "Scripts" / "python.exe")


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _context_is_useful(ctx: dict) -> bool:
    has_memories  = len(ctx.get("semantic",    {}).get("memories",   [])) > 0
    has_deadlines = len(ctx.get("structured",  {}).get("deadlines",  [])) > 0
    has_schedule  = bool(ctx.get("structured", {}).get("schedule",   {}).get("free_blocks"))
    has_behavioral = bool(ctx.get("behavioral", {}).get("work_style"))
    return has_memories or has_deadlines or has_schedule or has_behavioral


def _today() -> str:
    return datetime.now().strftime("%A, %B %d, %Y")


def _context_to_briefing(ctx: dict) -> str:
    lines = [f"Today is {_today()}."]
    behavioral = ctx.get("behavioral", {})
    if behavioral.get("work_style"):
        hours = ", ".join(behavioral.get("peak_focus_hours", []))
        conf  = behavioral.get("confidence", 0)
        lines.append(
            f"Work style: {behavioral['work_style']}, peak focus at {hours} "
            f"({conf:.0%} confidence, from {behavioral.get('inferred_from', 'behavioral data')})."
        )
    structured = ctx.get("structured", {})
    deadlines = structured.get("deadlines", [])
    if deadlines:
        dl = "; ".join(
            f"{d.get('course','')} {d.get('assignment','')} due {d.get('due_date','')} ({d.get('urgency','')})"
            for d in deadlines
        )
        lines.append(f"Deadlines: {dl}.")
    free = structured.get("schedule", {}).get("free_blocks", [])
    if free:
        lines.append("Available time slots: " + ", ".join(free[:4]) + ".")
    memories = ctx.get("semantic", {}).get("memories", [])
    if memories:
        mem = "\n".join(f"  - ({m['source']}) {m['text'][:120]}" for m in memories[:4])
        lines.append(f"Relevant history:\n{mem}")
    note = ctx.get("agent_note", "")
    if note:
        lines.append(f"Note: {note}")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# CUSTOM (direct Anthropic SDK — reference baseline)
# ══════════════════════════════════════════════════════════════════════════════

def naive_agent(task: str) -> str:
    """Plain Claude — no personal context."""
    r = client.messages.create(
        model=MODEL, max_tokens=600,
        system="You are a helpful personal assistant.",
        messages=[{"role": "user", "content": task}],
    )
    return r.content[0].text


def enhanced_agent_with_context(task: str, ctx: dict = None) -> str:
    """Claude with pre-fetched PersonalContext injected as a briefing."""
    if ctx is None:
        ctx = get_context(task)
    if not _context_is_useful(ctx):
        return naive_agent(task)
    briefing = _context_to_briefing(ctx)
    r = client.messages.create(
        model=MODEL, max_tokens=600,
        system=(
            "You are a helpful personal assistant who already knows the user well.\n\n"
            f"Personal context:\n{briefing}\n\n"
            "Answer directly using these details. Do not ask for info already covered."
        ),
        messages=[{"role": "user", "content": task}],
    )
    return r.content[0].text


def custom_enhanced_agent(task: str) -> tuple[str, dict]:
    ctx = get_context(task)
    return enhanced_agent_with_context(task, ctx), ctx


# ══════════════════════════════════════════════════════════════════════════════
# LANGCHAIN
# ══════════════════════════════════════════════════════════════════════════════

def langchain_naive_agent(task: str) -> str:
    """LangChain ReAct agent — no tools, no context."""
    from langchain_anthropic import ChatAnthropic
    from langgraph.prebuilt import create_react_agent

    llm   = ChatAnthropic(model=MODEL, temperature=0, max_tokens=600)
    agent = create_react_agent(llm, tools=[])
    result = agent.invoke({"messages": [("user", task)]})
    return result["messages"][-1].content


def langchain_enhanced_agent(task: str) -> tuple[str, dict]:
    """
    LangChain ReAct agent with PersonalContext registered as a native tool.
    The agent decides when to call get_personal_context based on the task.
    """
    from langchain_anthropic import ChatAnthropic
    from langchain_core.tools import tool
    from langgraph.prebuilt import create_react_agent

    # Fetch context for UI display (also available to the agent via the tool)
    ctx = get_context(task)

    @tool
    def get_personal_context(query: str) -> str:
        """
        Get personal context relevant to a task.
        Returns structured context including schedule, deadlines,
        behavioral patterns, and relevant memories.
        Call this before answering any personal question.
        """
        result = get_context(query)
        return json.dumps(result, indent=2)

    llm   = ChatAnthropic(model=MODEL, temperature=0, max_tokens=800)
    agent = create_react_agent(llm, tools=[get_personal_context])
    result = agent.invoke({
        "messages": [
            ("system", f"Today is {_today()}. Use get_personal_context before answering personal questions."),
            ("user", task),
        ]
    })
    # Last message is the final AI response
    return result["messages"][-1].content, ctx


# ══════════════════════════════════════════════════════════════════════════════
# CREWAI
# ══════════════════════════════════════════════════════════════════════════════

def crewai_naive_agent(task: str) -> str:
    """CrewAI agent — no context tools."""
    from crewai import Agent, Task, Crew

    assistant = Agent(
        role="Personal Assistant",
        goal="Help the user complete their task accurately.",
        backstory="You are a helpful assistant with no access to personal data.",
        llm=f"anthropic/{MODEL}",
        verbose=False,
        allow_delegation=False,
    )
    t = Task(
        description=task,
        agent=assistant,
        expected_output="A helpful, direct response to the user's request.",
    )
    crew = Crew(agents=[assistant], tasks=[t], verbose=False)
    result = crew.kickoff()
    return str(result)


def crewai_enhanced_agent(task: str) -> tuple[str, dict]:
    """CrewAI agent with PersonalContext as a BaseTool."""
    from crewai import Agent, Task, Crew
    from crewai.tools import BaseTool
    from pydantic import Field

    ctx = get_context(task)

    class PersonalContextTool(BaseTool):
        name: str = "get_personal_context"
        description: str = (
            "Get personal context relevant to a task — schedule, deadlines, "
            "behavioral patterns, and memories. Always call this first."
        )

        def _run(self, task: str) -> str:
            return json.dumps(get_context(task), indent=2)

    assistant = Agent(
        role="Personal Assistant",
        goal="Help the user with tasks using their personal context data.",
        backstory=(
            f"Today is {_today()}. You are a knowledgeable personal assistant with access "
            "to the user's calendar, email history, assignments, and behavioral patterns."
        ),
        tools=[PersonalContextTool()],
        llm=f"anthropic/{MODEL}",
        verbose=False,
        allow_delegation=False,
    )
    t = Task(
        description=task,
        agent=assistant,
        expected_output=(
            "A specific, personalized response that references real data from "
            "the user's personal context — actual times, course names, deadlines."
        ),
    )
    crew = Crew(agents=[assistant], tasks=[t], verbose=False)
    result = crew.kickoff()
    return str(result), ctx


# ══════════════════════════════════════════════════════════════════════════════
# LLAMAINDEX
# ══════════════════════════════════════════════════════════════════════════════

def llamaindex_naive_agent(task: str) -> str:
    """LlamaIndex ReActAgent — no tools."""
    from llama_index.core.agent import ReActAgent
    from llama_index.llms.anthropic import Anthropic as AnthropicLLM

    llm   = AnthropicLLM(model=MODEL, max_tokens=600)
    agent = ReActAgent.from_tools([], llm=llm, verbose=False)
    return str(agent.chat(task))


def llamaindex_enhanced_agent(task: str) -> tuple[str, dict]:
    """LlamaIndex ReActAgent with PersonalContext as a FunctionTool."""
    from llama_index.core.agent import ReActAgent
    from llama_index.core.tools import FunctionTool
    from llama_index.llms.anthropic import Anthropic as AnthropicLLM

    ctx = get_context(task)

    def personal_context_fn(query: str) -> str:
        """
        Get personal context relevant to a task.
        Returns schedule, deadlines, behavioral patterns, and memories.
        """
        return json.dumps(get_context(query), indent=2)

    context_tool = FunctionTool.from_defaults(
        fn=personal_context_fn,
        name="get_personal_context",
        description=(
            "Get personal context relevant to a task. Returns structured data "
            "including calendar free blocks, deadlines, work style, and relevant "
            "memories from email and calendar history. Call before answering."
        ),
    )

    llm   = AnthropicLLM(model=MODEL, max_tokens=800)
    agent = ReActAgent.from_tools(
        [context_tool], llm=llm, verbose=False,
        system_prompt=f"Today is {_today()}. Always call get_personal_context before answering.",
    )
    return str(agent.chat(task)), ctx


# ══════════════════════════════════════════════════════════════════════════════
# RAW MCP
# ══════════════════════════════════════════════════════════════════════════════

async def _mcp_call(task: str) -> tuple[str, dict]:
    """Connect to the PersonalContext MCP server and call get_personal_context."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    server_params = StdioServerParameters(
        command=PYTHON,
        args=[CONTEXT_SERVER],
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "get_personal_context", {"task": task}
            )
            ctx = json.loads(result.content[0].text)

    briefing = _context_to_briefing(ctx)
    r = client.messages.create(
        model=MODEL, max_tokens=600,
        system=(
            "You are a helpful personal assistant.\n\n"
            f"Personal context retrieved via MCP:\n{briefing}\n\n"
            "Answer directly using these details."
        ),
        messages=[{"role": "user", "content": task}],
    )
    return r.content[0].text, ctx


def mcp_naive_agent(task: str) -> str:
    """Plain Claude — no MCP context call."""
    return naive_agent(task)


def mcp_enhanced_agent(task: str) -> tuple[str, dict]:
    """
    Calls the PersonalContext MCP server via the stdio protocol,
    then uses the returned context to answer the task.
    """
    return asyncio.run(_mcp_call(task))


# ══════════════════════════════════════════════════════════════════════════════
# Platform dispatch table
# ══════════════════════════════════════════════════════════════════════════════

PLATFORM_AGENTS = {
    "LangChain":    (langchain_naive_agent,   langchain_enhanced_agent),
    "CrewAI":       (crewai_naive_agent,       crewai_enhanced_agent),
    "LlamaIndex":   (llamaindex_naive_agent,   llamaindex_enhanced_agent),
    "Raw MCP":      (mcp_naive_agent,          mcp_enhanced_agent),
    "Custom agent": (naive_agent,              custom_enhanced_agent),
}


def get_agents(platform: str):
    """
    Returns (naive_fn, enhanced_fn) for a platform.
    naive_fn(task) -> str
    enhanced_fn(task) -> (str, dict)   [response, context_used]
    """
    return PLATFORM_AGENTS.get(platform, PLATFORM_AGENTS["Custom agent"])
