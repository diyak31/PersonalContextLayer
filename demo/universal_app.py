"""
PersonalContext — Universal VC Demo

Three-step wizard:
  1. Configure your data sources
  2. Build your context layer
  3. See how it improves agents on popular platforms

Run with:
    streamlit run demo/universal_app.py
"""

import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import streamlit as st

ROOT       = Path(__file__).parent.parent
AGENT_DIR  = ROOT / "agent"
RAW_DIR    = AGENT_DIR / "data" / "raw"
DB_DIR     = AGENT_DIR / "db"
PYTHON     = str(ROOT / "agent" / ".venv" / "Scripts" / "python.exe")

sys.path.insert(0, str(ROOT / "context-mcp"))
sys.path.insert(0, str(Path(__file__).parent))

from agents import naive_agent, enhanced_agent_with_context
from context_engine import get_context
from app import render_context_panel, render_diff_bar, render_explain, count_specifics

# ── Page config ────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="PersonalContext",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
  /* ── Base ── */
  .stApp { background: #09090f; }
  section[data-testid="stSidebar"] { display: none; }
  * { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
  h1 { color: #f0f0f8 !important; font-size: 2rem !important; font-weight: 700; }
  h2 { color: #f0f0f8 !important; font-size: 1.2rem !important; font-weight: 600; }
  h3 { color: #7070a0 !important; font-size: 0.78rem !important;
       text-transform: uppercase; letter-spacing: 0.1em; font-weight: 600; }
  p, li, label, .stMarkdown { color: #b0b0c8; }
  hr { border-color: #1e1e30 !important; margin: 2rem 0 !important; }

  /* ── Step indicator ── */
  .step-bar {
    display: flex; align-items: center; gap: 0; margin: 1.5rem 0 2.5rem;
  }
  .step-node {
    display: flex; align-items: center; justify-content: center;
    width: 36px; height: 36px; border-radius: 50%;
    font-size: 0.85rem; font-weight: 700; flex-shrink: 0;
  }
  .step-node.active   { background: #5560e0; color: #fff; }
  .step-node.done     { background: #206040; color: #60e090; }
  .step-node.inactive { background: #1a1a2a; color: #505070; border: 1px solid #2a2a3a; }
  .step-label { font-size: 0.82rem; font-weight: 500; margin-left: 8px; }
  .step-label.active   { color: #9090e0; }
  .step-label.done     { color: #50b070; }
  .step-label.inactive { color: #404060; }
  .step-line { flex: 1; height: 1px; background: #1e1e30; margin: 0 12px; }

  /* ── Source cards ── */
  .src-card {
    background: #0f0f1c; border: 1px solid #1e1e30;
    border-radius: 12px; padding: 16px 14px;
    transition: border-color 0.15s;
  }
  .src-card.connected { border-color: #1e3a2a; }
  .src-card.selected  { border-color: #3a3a7a; background: #0f0f26; }
  .src-icon { font-size: 1.5rem; margin-bottom: 6px; }
  .src-name { font-size: 0.9rem; font-weight: 600; color: #d0d0e8; }
  .src-desc { font-size: 0.75rem; color: #606080; margin-top: 2px; }
  .badge-ok  { display:inline-block; background:#0d2a1a; color:#40b060;
               border:1px solid #1a4a2a; border-radius:4px;
               padding:1px 7px; font-size:0.7rem; font-weight:600; }
  .badge-no  { display:inline-block; background:#1e1e2a; color:#505070;
               border:1px solid #2a2a3a; border-radius:4px;
               padding:1px 7px; font-size:0.7rem; }

  /* ── Build progress ── */
  .build-row {
    display: flex; align-items: center; gap: 12px;
    padding: 10px 0; border-bottom: 1px solid #1a1a28;
  }
  .build-name { flex: 1; font-size: 0.88rem; color: #c0c0d8; }
  .build-stat { font-size: 0.78rem; color: #6060a0; }
  .build-done { font-size: 0.9rem; }

  /* ── Comparison panels ── */
  .cmp-panel {
    background: #0f0f1c; border: 1px solid #1e1e30;
    border-radius: 12px; padding: 20px; min-height: 200px;
  }
  .cmp-panel.naive    { border-top: 3px solid #8b3030; }
  .cmp-panel.enhanced { border-top: 3px solid #306050; }
  .cmp-label { font-size: 0.72rem; text-transform: uppercase;
               letter-spacing: 0.08em; font-weight: 700; margin-bottom: 10px; }
  .cmp-label.naive    { color: #c05050; }
  .cmp-label.enhanced { color: #40a070; }
  .cmp-body { font-size: 0.9rem; color: #c0c0d8; line-height: 1.6; }

  /* ── Metrics ── */
  .metric-row { display:flex; gap:10px; margin-top:12px; }
  .metric-box { flex:1; background:#0f0f1c; border:1px solid #1e1e30;
                border-radius:8px; padding:10px; text-align:center; }
  .metric-val { font-size:1.5rem; font-weight:700; color:#f0f0f8; }
  .metric-lbl { font-size:0.7rem; color:#5050a0; text-transform:uppercase;
                letter-spacing:0.06em; margin-top:2px; }
  .metric-delta { font-size:0.75rem; color:#40b060; }

  /* ── Platform tabs ── */
  .stTabs [data-baseweb="tab-list"] {
    background:#0f0f1c; border:1px solid #1e1e30;
    border-radius:10px; padding:4px; gap:4px;
  }
  .stTabs [data-baseweb="tab"] {
    background:transparent; color:#5050a0; border-radius:8px;
    font-weight:500; font-size:0.88rem;
  }
  .stTabs [aria-selected="true"] {
    background:#1e1e30 !important; color:#d0d0f0 !important;
  }

  /* ── Snippet box ── */
  .snippet {
    background:#060610; border:1px solid #1e1e2a;
    border-radius:8px; padding:16px;
    font-family:"SF Mono","Fira Code",monospace; font-size:0.8rem;
    color:#a0b0c0; line-height:1.7; overflow-x:auto;
    white-space:pre;
  }
  .kw  { color:#9090e0; }
  .fn  { color:#60c0e0; }
  .str { color:#80c080; }
  .cm  { color:#404060; font-style:italic; }

  /* ── Data trail ── */
  .trail-card {
    background:#0d0d18; border:1px solid #1e1e30;
    border-radius:10px; padding:16px; height:100%;
  }
  .trail-card h4 { color:#7070b0 !important; font-size:0.75rem !important;
                   text-transform:uppercase; letter-spacing:0.08em;
                   margin-bottom:10px; }
  .trail-item {
    display:flex; align-items:flex-start; gap:8px;
    padding:7px 0; border-bottom:1px solid #15152a;
    font-size:0.83rem; color:#a0a0c0; line-height:1.4;
  }
  .trail-item:last-child { border-bottom:none; }
  .trail-source {
    font-size:0.68rem; color:#505080; background:#0f0f1e;
    border:1px solid #1e1e30; border-radius:4px;
    padding:1px 6px; white-space:nowrap; margin-top:1px;
  }

  /* ── Buttons ── */
  button[kind="primary"] {
    background: linear-gradient(135deg,#5060d0,#3a70b0) !important;
    border:none !important; border-radius:9px !important;
    color:#fff !important; font-weight:600 !important;
    padding:10px 28px !important;
  }
  div[data-testid="column"] .stButton button {
    background:#0f0f1c; border:1px solid #1e1e30;
    color:#8080b0; border-radius:8px; width:100%;
    transition:all 0.15s; font-size:0.85rem;
  }
  div[data-testid="column"] .stButton button:hover {
    background:#1a1a2c; border-color:#4040a0; color:#d0d0f0;
  }
</style>
""", unsafe_allow_html=True)

# ── Data ───────────────────────────────────────────────────────────────────────

SOURCES = [
    {
        "id":    "gmail",
        "icon":  "📧",
        "name":  "Gmail",
        "desc":  "Email history, sent messages, receipts",
        "check": lambda: (ROOT / "gmail-mcp" / "token.json").exists(),
        "setup": "cd gmail-mcp && python auth.py",
        "file":  "gmail.jsonl",
    },
    {
        "id":    "gcal",
        "icon":  "📅",
        "name":  "Google Calendar",
        "desc":  "Events, meetings, free/busy schedule",
        "check": lambda: (ROOT / "gcal-mcp" / "token.json").exists(),
        "setup": "cd gcal-mcp && python auth.py",
        "file":  "gcal.jsonl",
    },
    {
        "id":    "canvas",
        "icon":  "📚",
        "name":  "Canvas LMS",
        "desc":  "Courses, assignments, deadlines",
        "check": lambda: bool(os.environ.get("CANVAS_TOKEN")),
        "setup": "Set CANVAS_TOKEN in agent/.env",
        "file":  "canvas.jsonl",
    },
    {
        "id":    "course_websites",
        "icon":  "🌐",
        "name":  "Course Websites",
        "desc":  "Scraped schedules and deadlines",
        "check": lambda: True,
        "setup": None,
        "file":  "course_websites.jsonl",
    },
    {
        "id":    "notion",
        "icon":  "📝",
        "name":  "Notion",
        "desc":  "Notes, documents, databases",
        "check": lambda: bool(os.environ.get("NOTION_TOKEN")),
        "setup": "Add NOTION_TOKEN to agent/.env",
        "file":  None,
    },
    {
        "id":    "github",
        "icon":  "🐙",
        "name":  "GitHub",
        "desc":  "Commits, pull requests, issues",
        "check": lambda: bool(os.environ.get("GITHUB_TOKEN")),
        "setup": "Add GITHUB_TOKEN to agent/.env",
        "file":  None,
    },
    {
        "id":    "slack",
        "icon":  "💬",
        "name":  "Slack",
        "desc":  "Messages, threads, channels",
        "check": lambda: bool(os.environ.get("SLACK_TOKEN")),
        "setup": "Add SLACK_TOKEN to agent/.env",
        "file":  None,
    },
    {
        "id":    "linear",
        "icon":  "📊",
        "name":  "Linear",
        "desc":  "Tasks, projects, engineering cycles",
        "check": lambda: bool(os.environ.get("LINEAR_TOKEN")),
        "setup": "Add LINEAR_TOKEN to agent/.env",
        "file":  None,
    },
]

PLATFORMS = {
    "🦜 LangChain": {
        "key":     "langchain",
        "install": "pip install langchain-anthropic langchain-mcp-adapters langgraph",
        "lines": [
            ('<span class="kw">from</span> langchain_mcp_adapters.tools <span class="kw">import</span> <span class="fn">load_mcp_tools</span>', None),
            ('<span class="kw">from</span> langgraph.prebuilt <span class="kw">import</span> <span class="fn">create_react_agent</span>', None),
            ('', None),
            ('<span class="cm"># Load PersonalContext as native LangChain tools — 1 line</span>', None),
            ('<span class="fn">tools</span> = <span class="kw">await</span> <span class="fn">load_mcp_tools</span>(session)', "highlight"),
            ('<span class="fn">agent</span> = <span class="fn">create_react_agent</span>(llm, tools)', None),
            ('<span class="fn">result</span> = <span class="kw">await</span> agent.<span class="fn">ainvoke</span>({<span class="str">"messages"</span>: [(<span class="str">"user"</span>, task)]})', None),
        ],
    },
    "🤝 CrewAI": {
        "key":     "crewai",
        "install": "pip install crewai",
        "lines": [
            ('<span class="kw">from</span> crewai.tools <span class="kw">import</span> <span class="fn">BaseTool</span>', None),
            ('<span class="kw">from</span> context_engine <span class="kw">import</span> <span class="fn">get_context</span>', None),
            ('', None),
            ('<span class="kw">class</span> <span class="fn">PersonalContextTool</span>(BaseTool):', None),
            ('    name = <span class="str">"get_personal_context"</span>', None),
            ('    <span class="kw">def</span> <span class="fn">_run</span>(self, task): <span class="kw">return</span> <span class="fn">str</span>(<span class="fn">get_context</span>(task))', "highlight"),
            ('', None),
            ('agent = Agent(tools=[<span class="fn">PersonalContextTool</span>()], llm=<span class="str">"claude-sonnet-4-6"</span>)', None),
        ],
    },
    "🦙 LlamaIndex": {
        "key":     "llamaindex",
        "install": "pip install llama-index llama-index-llms-anthropic",
        "lines": [
            ('<span class="kw">from</span> llama_index.core.tools <span class="kw">import</span> <span class="fn">FunctionTool</span>', None),
            ('<span class="kw">from</span> context_engine <span class="kw">import</span> <span class="fn">get_context</span>', None),
            ('', None),
            ('<span class="cm"># PersonalContext becomes a LlamaIndex tool in one line</span>', None),
            ('<span class="fn">tool</span> = <span class="fn">FunctionTool.from_defaults</span>(', None),
            ('    fn=<span class="fn">get_context</span>, name=<span class="str">"personal_context"</span>)', "highlight"),
            ('agent = <span class="fn">ReActAgent.from_tools</span>([tool], llm=Anthropic())', None),
            ('<span class="fn">response</span> = agent.<span class="fn">chat</span>(task)', None),
        ],
    },
    "🔌 Raw MCP": {
        "key":     "mcp",
        "install": "pip install mcp  # Python, TypeScript, Go, Rust — any MCP SDK",
        "lines": [
            ('<span class="kw">async with</span> <span class="fn">stdio_client</span>(server) <span class="kw">as</span> (read, write):', None),
            ('    <span class="kw">async with</span> <span class="fn">ClientSession</span>(read, write) <span class="kw">as</span> session:', None),
            ('        <span class="kw">await</span> session.<span class="fn">initialize</span>()', None),
            ('', None),
            ('        <span class="cm"># One call — works in any language with an MCP SDK</span>', None),
            ('        ctx = <span class="kw">await</span> session.<span class="fn">call_tool</span>(', "highlight"),
            ('            <span class="str">"get_personal_context"</span>, {<span class="str">"task"</span>: task})', "highlight"),
        ],
    },
}

DEMO_TASKS = {
    "📅  Find study time":   "Find me a 2-hour focused study block for my CS231N final this week.",
    "📧  Email a professor": "Draft an email to my professor asking for a deadline extension on my CS231N project.",
    "📋  Plan my week":      "Given my deadlines, what should I prioritize this week?",
}

# ── Session state defaults ─────────────────────────────────────────────────────

if "step" not in st.session_state:
    st.session_state["step"] = 1
if "selected_sources" not in st.session_state:
    st.session_state["selected_sources"] = [
        s["id"] for s in SOURCES if s["check"]()
    ]
if "context_built" not in st.session_state:
    st.session_state["context_built"] = DB_DIR.exists()

# ── Helpers (count_specifics imported from app) ────────────────────────────────


def jsonl_count(filename: str) -> int:
    path = RAW_DIR / filename
    if not path.exists():
        return 0
    return sum(1 for _ in open(path, encoding="utf-8", errors="ignore"))


def chroma_total() -> int:
    try:
        import chromadb
        from chromadb.utils import embedding_functions
        client = chromadb.PersistentClient(path=str(DB_DIR))
        col = client.get_collection("personal_memory")
        return col.count()
    except Exception:
        return 0


def step_class(n: int) -> str:
    s = st.session_state["step"]
    if n < s:  return "done"
    if n == s: return "active"
    return "inactive"


# ── Step indicator ─────────────────────────────────────────────────────────────

def render_step_bar():
    steps = ["Configure sources", "Build context layer", "Test on platforms"]
    nodes, labels = [], []
    for i, label in enumerate(steps, 1):
        cls = step_class(i)
        icon = "✓" if cls == "done" else str(i)
        nodes.append(f'<div class="step-node {cls}">{icon}</div>')
        labels.append(f'<span class="step-label {cls}">{label}</span>')

    html = '<div class="step-bar">'
    for i, (node, label) in enumerate(zip(nodes, labels)):
        html += node + label
        if i < len(nodes) - 1:
            html += '<div class="step-line"></div>'
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


# ── Header ─────────────────────────────────────────────────────────────────────

st.markdown("# 🧠 PersonalContext")
st.markdown(
    "Build a personal context layer from your data. "
    "Plug it into any agent framework. Watch performance improve."
)
render_step_bar()

# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — Configure sources
# ══════════════════════════════════════════════════════════════════════════════

with st.container():
    st.markdown("## Step 1 — Configure your context sources")
    st.markdown(
        "Select which data sources to include. "
        "Connected sources have valid credentials and are ready to ingest."
    )
    st.markdown("")

    cols = st.columns(4)
    selected = list(st.session_state["selected_sources"])

    for i, src in enumerate(SOURCES):
        with cols[i % 4]:
            connected = src["check"]()
            is_sel    = src["id"] in selected
            badge     = '<span class="badge-ok">Connected ✓</span>' if connected else '<span class="badge-no">Not connected</span>'

            st.markdown(
                f'<div class="src-card {"connected" if connected else ""} {"selected" if is_sel else ""}">'
                f'<div class="src-icon">{src["icon"]}</div>'
                f'<div class="src-name">{src["name"]}</div>'
                f'<div class="src-desc">{src["desc"]}</div>'
                f'<div style="margin-top:8px">{badge}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            if connected:
                checked = st.checkbox(
                    "Include",
                    value=is_sel,
                    key=f"chk_{src['id']}",
                    label_visibility="collapsed",
                )
                if checked and src["id"] not in selected:
                    selected.append(src["id"])
                elif not checked and src["id"] in selected:
                    selected.remove(src["id"])
            elif src["setup"]:
                st.caption(f"`{src['setup']}`")

    st.session_state["selected_sources"] = selected

    active_count = len(selected)
    st.markdown("")
    c1, c2 = st.columns([4, 1])
    with c1:
        st.markdown(
            f"**{active_count} source{'s' if active_count != 1 else ''} selected:** "
            + ", ".join(
                f"`{s['id']}`" for s in SOURCES if s["id"] in selected
            )
        )
    with c2:
        if st.button("Continue →", type="primary", disabled=active_count == 0, key="step1_continue"):
            st.session_state["step"] = max(st.session_state["step"], 2)
            st.rerun()

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — Build context layer
# ══════════════════════════════════════════════════════════════════════════════

step2_locked = st.session_state["step"] < 2

with st.container():
    if step2_locked:
        st.markdown("## Step 2 — Build context layer  *(complete Step 1 first)*")
    else:
        st.markdown("## Step 2 — Build your context layer")

    if not step2_locked:
        selected_ids = st.session_state["selected_sources"]
        total_vectors = chroma_total()
        already_built = total_vectors > 0

        if already_built:
            st.success(
                f"✅ Context layer ready — **{total_vectors:,} vectors** "
                f"across {len(selected_ids)} sources"
            )

        st.markdown("**Source status**")
        for src in SOURCES:
            if src["id"] not in selected_ids:
                continue
            count = jsonl_count(src["file"]) if src["file"] else 0
            built = count > 0

            label_html = (
                f'<div class="build-row">'
                f'<span style="font-size:1.1rem">{src["icon"]}</span>'
                f'<span class="build-name">{src["name"]}</span>'
                f'<span class="build-stat">'
                + (f"{count:,} records" if built else "not yet ingested")
                + f'</span>'
                f'<span class="build-done">{"✅" if built else "⬜"}</span>'
                f'</div>'
            )
            st.markdown(label_html, unsafe_allow_html=True)

        st.markdown("")
        col_build, col_next = st.columns([2, 1])

        with col_build:
            rebuild = st.button(
                "🔄 Rebuild from source" if already_built else "▶ Build context layer",
                type="primary" if not already_built else "secondary",
            )

        with col_next:
            if st.button("Continue →", type="primary", disabled=not already_built, key="step2_continue"):
                st.session_state["step"] = max(st.session_state["step"], 3)
                st.rerun()

        if rebuild:
            selected_ids = st.session_state["selected_sources"]
            log = st.empty()
            progress = st.progress(0)
            lines = []

            ingest_sources = [
                s for s in SOURCES
                if s["id"] in selected_ids and s["file"]
            ]
            total_steps = len(ingest_sources) + 1

            for idx, src in enumerate(ingest_sources):
                lines.append(f"📥 Ingesting {src['name']}…")
                log.code("\n".join(lines))
                progress.progress((idx + 0.5) / total_steps)

                result = subprocess.run(
                    [PYTHON, str(AGENT_DIR / "ingest.py"),
                     "--source", src["id"]],
                    capture_output=True, text=True, cwd=str(AGENT_DIR),
                )
                count = jsonl_count(src["file"])
                lines[-1] = f"✅ {src['name']} — {count:,} records"
                log.code("\n".join(lines))
                progress.progress((idx + 1) / total_steps)

            lines.append("⚙️  Embedding vectors…")
            log.code("\n".join(lines))
            subprocess.run(
                [PYTHON, str(AGENT_DIR / "embed.py"), "--reset"],
                capture_output=True, text=True, cwd=str(AGENT_DIR),
            )
            total_vectors = chroma_total()
            lines[-1] = f"✅ Embedded {total_vectors:,} vectors"
            log.code("\n".join(lines))
            progress.progress(1.0)

            st.session_state["context_built"] = True
            st.success(f"✅ Context layer ready — {total_vectors:,} vectors")
            st.rerun()

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — Test on platforms
# ══════════════════════════════════════════════════════════════════════════════

step3_locked = st.session_state["step"] < 3

with st.container():
    if step3_locked:
        st.markdown("## Step 3 — Test on platforms  *(complete Step 2 first)*")
    else:
        st.markdown("## Step 3 — See the impact on popular agent platforms")
        st.markdown(
            "Same agent. Same task. Same platform. "
            "The only difference is one call to `get_personal_context()`."
        )
        st.markdown("")

        # Task picker
        st.markdown("### Choose a task")
        task_cols = st.columns(len(DEMO_TASKS))
        for col, (label, task) in zip(task_cols, DEMO_TASKS.items()):
            with col:
                if st.button(label, use_container_width=True, key=f"task_{label}"):
                    st.session_state["demo_task"] = task
                    st.session_state.pop("demo_ctx", None)
                    with st.spinner("Pre-loading context…"):
                        st.session_state["demo_ctx"] = get_context(task)

        custom = st.text_input(
            "Or enter a custom task:",
            value=st.session_state.get("demo_task", ""),
            placeholder="e.g. 'What should I work on tonight?'",
        )
        if custom:
            st.session_state["demo_task"] = custom

        task = st.session_state.get("demo_task", "")
        st.markdown("")

        # Platform tabs
        tab_objects = st.tabs(list(PLATFORMS.keys()))

        for tab, (plat_name, plat) in zip(tab_objects, PLATFORMS.items()):
            with tab:
                col_snippet, col_info = st.columns([3, 1])

                with col_snippet:
                    st.markdown("### Integration")
                    # Render styled snippet
                    html_lines = []
                    for line_html, style in plat["lines"]:
                        bg = "background:#1a1a3a;border-radius:3px;padding:0 4px;" if style == "highlight" else ""
                        html_lines.append(f'<div style="{bg}">{line_html}</div>')
                    st.markdown(
                        f'<div class="snippet">{"".join(html_lines)}</div>',
                        unsafe_allow_html=True,
                    )

                with col_info:
                    st.markdown("### Install")
                    st.code(plat["install"], language="bash")
                    st.markdown("### Tools exposed")
                    st.markdown(
                        "- `get_personal_context(task)`\n"
                        "- `get_profile()`\n"
                        "- `search_personal_memory(query)`"
                    )

                st.markdown("")
                st.markdown("### Live comparison")

                run_key = f"run_{plat['key']}"
                run = st.button(
                    "▶  Run comparison",
                    key=run_key,
                    type="primary",
                    disabled=not task,
                )

                if not task:
                    st.caption("Select a task above to run the comparison.")

                if run and task:
                    ctx = st.session_state.get("demo_ctx") or get_context(task)
                    st.session_state["demo_ctx"] = ctx

                    with st.spinner("Running agents in parallel…"):
                        with ThreadPoolExecutor(max_workers=2) as pool:
                            naive_f    = pool.submit(naive_agent, task)
                            enhanced_f = pool.submit(enhanced_agent_with_context, task, ctx)
                            naive_r    = naive_f.result()
                            enhanced_r = enhanced_f.result()

                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown(
                            f'<div class="cmp-panel naive">'
                            f'<div class="cmp-label naive">'
                            f'{plat_name.split()[1]} — no context</div>'
                            f'<div class="cmp-body">{naive_r}</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                    with c2:
                        st.markdown(
                            f'<div class="cmp-panel enhanced">'
                            f'<div class="cmp-label enhanced">'
                            f'{plat_name.split()[1]} + PersonalContext</div>'
                            f'<div class="cmp-body">{enhanced_r}</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

                    # ── Prominent diff bar ─────────────────────────────────
                    st.markdown("### Impact")
                    render_diff_bar(naive_r, enhanced_r, ctx)

                    # ── Memory layers + explain ────────────────────────────
                    st.markdown("### What powered the right answer")
                    mc1, mc2 = st.columns(2)
                    with mc1:
                        render_context_panel(ctx)
                    with mc2:
                        render_explain(
                            task, enhanced_r, ctx,
                            key=f"{plat['key']}_{hash(task) % 9999}"
                        )

                    with st.expander("View full PersonalContext object", expanded=False):
                        st.json(ctx)

        st.divider()
        st.markdown("### Ready to build your own agent?")
        st.markdown(
            "Use the **Agent Builder** to configure a system prompt, "
            "select tools, test live, and export deployment-ready code "
            "for LangChain, FastAPI, or raw Python."
        )
        st.code("streamlit run demo/builder_app.py", language="bash")
