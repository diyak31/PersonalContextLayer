"""
PersonalContext — Platform Integrations Demo

Shows how to plug the PersonalContext layer into popular agent frameworks.
Each tab: integration snippet + live before/after demo.

Run with:
    streamlit run demo/platforms_app.py
"""

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent / "context-mcp"))
sys.path.insert(0, str(Path(__file__).parent))

from agents import naive_agent, enhanced_agent_with_context
from context_engine import get_context

# ── Page config ────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="PersonalContext — Integrations",
    page_icon="🔌",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    .stApp { background: #0d0d12; }
    section[data-testid="stSidebar"] { display: none; }
    h1, h2 { color: #f0f0f5 !important; }
    h3 { color: #8888aa !important; font-size: 0.9rem !important;
         text-transform: uppercase; letter-spacing: 0.08em; }
    p, li, .stMarkdown { color: #c0c0d0; }
    hr { border-color: #22223a !important; }

    /* Code blocks */
    .stCode { background: #0a0a0f !important; border: 1px solid #22223a;
               border-radius: 8px; }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        background: #13131e;
        border-radius: 10px;
        padding: 4px;
        gap: 4px;
    }
    .stTabs [data-baseweb="tab"] {
        background: transparent;
        color: #8888aa;
        border-radius: 8px;
        font-weight: 500;
    }
    .stTabs [aria-selected="true"] {
        background: #22223a !important;
        color: #f0f0f5 !important;
    }

    /* Cards */
    .card {
        background: #13131e;
        border: 1px solid #22223a;
        border-radius: 12px;
        padding: 20px;
    }

    /* Platform badge */
    .badge {
        display: inline-block;
        border-radius: 6px;
        padding: 4px 12px;
        font-size: 0.8em;
        font-weight: 600;
        margin-bottom: 12px;
    }
    .badge-langchain  { background: #1a2e1a; color: #4caf50; border: 1px solid #2a4a2a; }
    .badge-crewai     { background: #1a1a2e; color: #7c7cf0; border: 1px solid #2a2a4a; }
    .badge-llamaindex { background: #2e1a1a; color: #f07070; border: 1px solid #4a2a2a; }
    .badge-mcp        { background: #1a2a2e; color: #50b0c0; border: 1px solid #2a4a50; }
    .badge-custom     { background: #2e2a1a; color: #c0a050; border: 1px solid #4a401a; }

    /* Result panels */
    .panel-naive    { background: #13131e; border: 1px solid #3a1515;
                      border-top: 3px solid #e05555; border-radius: 10px; padding: 16px; }
    .panel-enhanced { background: #13131e; border: 1px solid #153a15;
                      border-top: 3px solid #55c080; border-radius: 10px; padding: 16px; }

    button[kind="primary"] {
        background: linear-gradient(135deg, #5560e0, #4080c0) !important;
        border: none !important; border-radius: 8px !important;
        color: white !important; font-weight: 600 !important;
    }
</style>
""", unsafe_allow_html=True)

# ── Platform definitions ───────────────────────────────────────────────────────

PLATFORMS = {
    "🦜 LangChain": {
        "badge": ("badge-langchain", "LangChain + LangGraph"),
        "install": "pip install langchain-mcp-adapters langchain-anthropic langgraph",
        "description": "Load all PersonalContext tools directly into a LangGraph ReAct agent in two lines.",
        "snippet": '''\
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_anthropic import ChatAnthropic
from langgraph.prebuilt import create_react_agent
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = StdioServerParameters(command="python", args=["context-mcp/server.py"])

async def run(task: str) -> str:
    async with stdio_client(SERVER) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # PersonalContext tools load as native LangChain tools
            tools = await load_mcp_tools(session)

            model = ChatAnthropic(model="claude-sonnet-4-6")
            agent = create_react_agent(model, tools)
            result = await agent.ainvoke({"messages": [("user", task)]})
            return result["messages"][-1].content''',
    },
    "🤝 CrewAI": {
        "badge": ("badge-crewai", "CrewAI"),
        "install": "pip install crewai",
        "description": "Wrap PersonalContext as a CrewAI BaseTool and assign it to any agent or crew.",
        "snippet": '''\
from crewai import Agent, Task, Crew
from crewai.tools import BaseTool
import sys; sys.path.insert(0, "context-mcp")
from context_engine import get_context

class PersonalContextTool(BaseTool):
    name: str = "get_personal_context"
    description: str = "Get personal context relevant to a task"

    def _run(self, task: str) -> str:
        return str(get_context(task))

assistant = Agent(
    role="Personal Assistant",
    goal="Help the user with tasks using their personal context",
    backstory="You have access to the user's calendar, email, and history.",
    tools=[PersonalContextTool()],
    llm="claude-sonnet-4-6",
    verbose=False,
)
task = Task(description="{task}", agent=assistant, expected_output="Helpful response")
crew = Crew(agents=[assistant], tasks=[task])
result = crew.kickoff(inputs={"task": task_str})''',
    },
    "🦙 LlamaIndex": {
        "badge": ("badge-llamaindex", "LlamaIndex"),
        "install": "pip install llama-index llama-index-llms-anthropic",
        "description": "Register PersonalContext as a FunctionTool in a LlamaIndex ReAct agent.",
        "snippet": '''\
from llama_index.core.agent import ReActAgent
from llama_index.core.tools import FunctionTool
from llama_index.llms.anthropic import Anthropic
import sys; sys.path.insert(0, "context-mcp")
from context_engine import get_context

# One line: PersonalContext becomes a LlamaIndex tool
context_tool = FunctionTool.from_defaults(
    fn=get_context,
    name="personal_context",
    description="Get personal context for any task — schedule, "
                "email history, deadlines, preferences",
)

agent = ReActAgent.from_tools(
    [context_tool],
    llm=Anthropic(model="claude-sonnet-4-6"),
    verbose=False,
)
response = agent.chat(task)''',
    },
    "🔌 Raw MCP": {
        "badge": ("badge-mcp", "MCP Protocol"),
        "install": "pip install mcp  # any language with an MCP SDK",
        "description": "Call PersonalContext directly over the MCP protocol — works in Python, TypeScript, or any MCP-compatible runtime.",
        "snippet": '''\
# Python — direct MCP client
import asyncio, json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = StdioServerParameters(command="python", args=["context-mcp/server.py"])

async def run(task: str):
    async with stdio_client(SERVER) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "get_personal_context", {"task": task}
            )
            return json.loads(result.content[0].text)

# TypeScript — same interface, different runtime
/*
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const client = new Client({ name: "my-agent", version: "1.0.0" });
await client.connect(new StdioClientTransport({ command: "python", args: ["server.py"] }));
const ctx = await client.callTool({ name: "get_personal_context", arguments: { task } });
*/''',
    },
    "⚙️ Custom Agent": {
        "badge": ("badge-custom", "Any Custom Agent"),
        "install": "# No extra dependencies — import context_engine directly",
        "description": "Import the context engine directly for any custom agent. Zero framework overhead.",
        "snippet": '''\
import sys; sys.path.insert(0, "context-mcp")
from context_engine import get_context, get_user_profile
from anthropic import Anthropic

client = Anthropic()

def my_agent(task: str) -> str:
    # One call — that\'s it
    ctx = get_context(task)

    system = f"""You are a personal assistant.
User context: {ctx}
Answer directly using this context."""

    return client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        system=system,
        messages=[{"user": task}],
    ).content[0].text

# Works with OpenAI, Gemini, Ollama — swap the client, keep the context call
import openai
def openai_agent(task: str) -> str:
    ctx = get_context(task)
    return openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": f"Personal context: {ctx}"},
            {"role": "user",   "content": task},
        ],
    ).choices[0].message.content''',
    },
}

DEMO_TASKS = {
    "📅 Schedule study time": (
        "Find me a 2-hour focused study block for my CS231N final this week."
    ),
    "📧 Email a professor": (
        "Draft an email to my professor asking for a short extension on my CS231N project."
    ),
    "📋 Plan my week": (
        "Given my upcoming deadlines, what should I prioritize this week?"
    ),
}

# ── Helpers ────────────────────────────────────────────────────────────────────

def count_specifics(text: str) -> int:
    patterns = [
        r'\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b',
        r'\b\d{1,2}:\d{2}\s*(am|pm|AM|PM)?\b',
        r'\bCS\s*\d{3}[A-Z]?\b',
        r'\$\d+',
        r'\b\d+\s*(days?|hours?|weeks?)\b',
    ]
    return sum(len(re.findall(p, text, re.IGNORECASE)) for p in patterns)


def render_demo(platform_name: str):
    """Render the live demo section for a platform tab."""
    st.markdown("### Live demo")
    st.caption(
        "The context layer output is identical regardless of platform — "
        "only the wrapper code changes."
    )

    task_cols = st.columns(len(DEMO_TASKS))
    task_key  = f"task_{platform_name}"
    ctx_key   = f"ctx_{platform_name}"

    for col, (label, task) in zip(task_cols, DEMO_TASKS.items()):
        with col:
            if st.button(label, key=f"btn_{platform_name}_{label}", use_container_width=True):
                st.session_state[task_key] = task
                st.session_state.pop(ctx_key, None)
                with st.spinner("Pre-loading context…"):
                    st.session_state[ctx_key] = get_context(task)

    task = st.session_state.get(task_key, "")
    if task:
        st.caption(f"**Task:** *{task}*")

    run = st.button(
        "▶  Run",
        key=f"run_{platform_name}",
        type="primary",
        disabled=not task,
    )

    if run and task:
        context  = st.session_state.get(ctx_key) or get_context(task)
        c1, c2   = st.columns(2)

        with c1:
            st.markdown("**Without PersonalContext**")
        with c2:
            st.markdown(f"**Via {platform_name.split()[-1]}  +  PersonalContext**")

        with ThreadPoolExecutor(max_workers=2) as pool:
            naive_f    = pool.submit(naive_agent, task)
            enhanced_f = pool.submit(enhanced_agent_with_context, task, context)
            naive_r    = naive_f.result()
            enhanced_r = enhanced_f.result()

        naive_spec    = count_specifics(naive_r)
        enhanced_spec = count_specifics(enhanced_r)

        with c1:
            st.markdown(
                f'<div class="panel-naive">{naive_r}</div>',
                unsafe_allow_html=True,
            )
            st.caption(f"Specific entities: **{naive_spec}**")

        with c2:
            st.markdown(
                f'<div class="panel-enhanced">{enhanced_r}</div>',
                unsafe_allow_html=True,
            )
            st.caption(
                f"Specific entities: **{enhanced_spec}**  "
                f"{'(+' + str(enhanced_spec - naive_spec) + ')' if enhanced_spec > naive_spec else ''}"
            )

        with st.expander("View raw PersonalContext object", expanded=False):
            st.json(context)


# ── Header ─────────────────────────────────────────────────────────────────────

st.markdown("# 🔌 PersonalContext — Platform Integrations")
st.markdown(
    "The same context layer. Any agent framework. "
    "Pick your platform — the integration is always one tool call."
)

_src = json.loads((Path(__file__).parent.parent / "context-mcp" / "sources.json").read_text())
_active = [s["type"] for s in _src["active_sources"] if s["enabled"]]
st.markdown("**Active data sources:** " + "  ·  ".join(f"`{s}`" for s in _active))
st.divider()

# ── Platform tabs ──────────────────────────────────────────────────────────────

tabs = st.tabs(list(PLATFORMS.keys()))

for tab, (name, cfg) in zip(tabs, PLATFORMS.items()):
    with tab:
        badge_cls, badge_label = cfg["badge"]
        st.markdown(
            f'<span class="badge {badge_cls}">{badge_label}</span>',
            unsafe_allow_html=True,
        )
        st.markdown(cfg["description"])

        col_code, col_info = st.columns([3, 1])
        with col_code:
            st.markdown("**Integration snippet**")
            st.code(cfg["snippet"], language="python")
        with col_info:
            st.markdown("**Install**")
            st.code(cfg["install"], language="bash")
            st.markdown("**Tools available**")
            st.markdown(
                "- `get_personal_context(task)`\n"
                "- `get_profile()`\n"
                "- `search_personal_memory(query)`"
            )

        st.divider()
        render_demo(name)
