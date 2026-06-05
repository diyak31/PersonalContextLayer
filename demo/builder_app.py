"""
PersonalContext — Agent Builder

Configure a PersonalContext-powered agent, test it live against your data,
then export deployment-ready code for LangChain, FastAPI, or raw Python.

Run with:
    streamlit run demo/builder_app.py
"""

import io
import json
import sys
import textwrap
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import streamlit as st
from anthropic import Anthropic
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "context-mcp"))

from context_engine import get_context, get_user_profile, search_memory

load_dotenv(ROOT / "agent" / ".env")
client = Anthropic()

# ── Page config ────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="PersonalContext Builder",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
  .stApp { background: #09090f; }
  section[data-testid="stSidebar"] { display: none; }
  h1 { color:#f0f0f8 !important; font-size:1.8rem !important; font-weight:700; }
  h2 { color:#f0f0f8 !important; font-size:1rem !important; font-weight:600; }
  h3 { color:#6060a0 !important; font-size:0.72rem !important;
       text-transform:uppercase; letter-spacing:0.1em; }
  p, li, label, .stMarkdown { color:#a0a0c0; font-size:0.9rem; }
  hr { border-color:#1a1a28 !important; }

  /* Config panel */
  .config-panel {
    background:#0d0d18; border:1px solid #1a1a28;
    border-radius:12px; padding:20px; height:100%;
  }

  /* Textarea */
  textarea { background:#06060f !important; color:#c0c0e0 !important;
             border:1px solid #1e1e30 !important; border-radius:8px !important;
             font-family:"SF Mono","Fira Code",monospace !important;
             font-size:0.82rem !important; }

  /* Inputs */
  input[type="text"] { background:#06060f !important; color:#c0c0e0 !important;
                       border:1px solid #1e1e30 !important; border-radius:8px !important; }
  select, .stSelectbox div { background:#06060f !important; }

  /* Tabs */
  .stTabs [data-baseweb="tab-list"] {
    background:#0d0d18; border:1px solid #1a1a28;
    border-radius:10px; padding:4px; gap:4px;
  }
  .stTabs [data-baseweb="tab"] {
    background:transparent; color:#505080;
    border-radius:8px; font-size:0.85rem; font-weight:500;
  }
  .stTabs [aria-selected="true"] {
    background:#1a1a2c !important; color:#d0d0f0 !important;
  }

  /* Response panels */
  .resp-panel {
    background:#0d0d18; border:1px solid #1a1a28;
    border-radius:10px; padding:16px; min-height:140px;
  }
  .resp-label { font-size:0.68rem; text-transform:uppercase;
                letter-spacing:0.08em; font-weight:700; margin-bottom:8px; }
  .resp-naive    .resp-label { color:#804040; }
  .resp-enhanced .resp-label { color:#408060; }
  .resp-body { font-size:0.87rem; color:#b0b0c8; line-height:1.6; }

  /* Tool chips */
  .tool-chip {
    display:inline-block; background:#0f0f1e; border:1px solid #1e1e30;
    border-radius:6px; padding:4px 10px; font-size:0.78rem;
    color:#7070b0; margin:2px;
  }
  .tool-chip.active { background:#12122a; border-color:#3a3a7a; color:#9090e0; }

  /* Metric pills */
  .pill {
    display:inline-block; border-radius:20px; padding:3px 10px;
    font-size:0.75rem; font-weight:600; margin-right:6px;
  }
  .pill-green { background:#0d2a1a; color:#40b060; border:1px solid #1a4a2a; }
  .pill-red   { background:#2a0d0d; color:#b04040; border:1px solid #4a1a1a; }
  .pill-blue  { background:#0d1a2a; color:#4090c0; border:1px solid #1a3a4a; }

  /* Buttons */
  button[kind="primary"] {
    background:linear-gradient(135deg,#5060d0,#3a70b0) !important;
    border:none !important; border-radius:8px !important;
    color:#fff !important; font-weight:600 !important;
  }
  .stDownloadButton button {
    background:#0d0d18 !important; border:1px solid #2a2a4a !important;
    color:#8080c0 !important; border-radius:8px !important;
    font-size:0.82rem !important;
  }
</style>
""", unsafe_allow_html=True)

# ── Code generation ────────────────────────────────────────────────────────────

TOOL_DEFS = {
    "get_personal_context": {
        "label": "get_personal_context",
        "desc":  "Retrieve context relevant to any task",
        "import": "get_context",
        "langchain": textwrap.dedent("""\
            @tool
            def get_personal_context(task: str) -> dict:
                \"\"\"Get personal context relevant to a task — schedule, emails, deadlines, preferences.\"\"\"
                return get_context(task)"""),
        "fastapi_call": "ctx = get_context(req.task)",
        "raw_call":     "ctx = get_context(task)",
    },
    "get_user_profile": {
        "label": "get_user_profile",
        "desc":  "Return the user's behavioral profile",
        "import": "get_user_profile",
        "langchain": textwrap.dedent("""\
            @tool
            def get_user_profile_tool() -> dict:
                \"\"\"Get the user's behavioral profile — work style, peak hours, contacts, courses.\"\"\"
                return get_user_profile()"""),
        "fastapi_call": "profile = get_user_profile()",
        "raw_call":     "profile = get_user_profile()",
    },
    "search_memory": {
        "label": "search_personal_memory",
        "desc":  "Semantic search over personal data",
        "import": "search_memory",
        "langchain": textwrap.dedent("""\
            @tool
            def search_personal_memory(query: str, source: str = None) -> list:
                \"\"\"Semantic search over personal data. Source: gmail | gcal | canvas | purchases.\"\"\"
                return search_memory(query, source=source)"""),
        "fastapi_call": "",
        "raw_call":     "",
    },
}

MODELS = {
    "claude-sonnet-4-6":        "Claude Sonnet 4.6  (recommended)",
    "claude-haiku-4-5-20251001":"Claude Haiku 4.5   (fastest)",
    "claude-opus-4-8":          "Claude Opus 4.8    (most capable)",
}

SYSTEM_PROMPT_PRESETS = {
    "Personal assistant": (
        "You are a knowledgeable personal assistant who already knows the user well. "
        "Use the personal context provided to give specific, grounded, actionable responses. "
        "Reference real names, dates, and details. Never ask for information already in the context."
    ),
    "Study planner": (
        "You are an academic study planner. Use the user's course deadlines, calendar, "
        "and behavioral patterns to create realistic, personalized study plans. "
        "Always reference specific assignments and real free time slots."
    ),
    "Email assistant": (
        "You are an email drafting assistant who knows the user's communication style "
        "from their email history. Match their tone and voice. Reference relevant context "
        "from past interactions when drafting replies or new messages."
    ),
    "Custom": "",
}


def generate_langchain(cfg: dict) -> str:
    selected = [k for k, v in cfg["tools"].items() if v]
    tool_defs  = "\n\n".join(TOOL_DEFS[k]["langchain"] for k in selected)
    tool_names = ", ".join(TOOL_DEFS[k]["label"] for k in selected)
    imports    = ", ".join(TOOL_DEFS[k]["import"] for k in selected) or "get_context"
    name       = cfg["name"] or "PersonalContextAgent"
    model      = cfg["model"]
    prompt     = cfg["system_prompt"].replace('"""', "'''")

    return textwrap.dedent(f'''\
        """
        {name} — PersonalContext Agent
        Framework : LangChain + LangServe
        Generated : PersonalContext Builder

        Run:
            pip install -r requirements.txt
            uvicorn agent_server:app --reload --port 8000

        Test:
            curl -X POST http://localhost:8000/agent/invoke \\
                 -H "Content-Type: application/json" \\
                 -d \'{{"input": {{"messages": [{{"type": "human", "content": "find me study time"}}]}}}}\'
        """

        import sys
        sys.path.insert(0, "context-mcp")

        from fastapi import FastAPI
        from langchain_anthropic import ChatAnthropic
        from langchain_core.tools import tool
        from langgraph.prebuilt import create_react_agent
        from langserve import add_routes

        from context_engine import {imports}

        # ── PersonalContext tools ──────────────────────────────────────────────

        {tool_defs}

        # ── Agent ──────────────────────────────────────────────────────────────

        SYSTEM_PROMPT = """{prompt}"""

        llm   = ChatAnthropic(model="{model}", temperature=0)
        agent = create_react_agent(llm, [{tool_names}], state_modifier=SYSTEM_PROMPT)

        # ── Server ─────────────────────────────────────────────────────────────

        app = FastAPI(
            title="{name}",
            description="Powered by PersonalContext — github.com/your-repo",
        )
        add_routes(app, agent, path="/agent")

        if __name__ == "__main__":
            import uvicorn
            uvicorn.run(app, host="0.0.0.0", port=8000)
    ''')


def generate_fastapi(cfg: dict) -> str:
    selected  = [k for k, v in cfg["tools"].items() if v]
    imports   = ", ".join(TOOL_DEFS[k]["import"] for k in selected) or "get_context"
    ctx_lines = "\n    ".join(
        TOOL_DEFS[k]["fastapi_call"] for k in selected if TOOL_DEFS[k]["fastapi_call"]
    ) or "ctx = {}"
    name  = cfg["name"] or "PersonalContextAgent"
    model = cfg["model"]
    prompt = cfg["system_prompt"].replace('"""', "'''")

    return textwrap.dedent(f'''\
        """
        {name} — PersonalContext Agent
        Framework : FastAPI + Anthropic
        Generated : PersonalContext Builder

        Run:
            pip install -r requirements.txt
            uvicorn agent_server:app --reload --port 8000

        Test:
            curl -X POST http://localhost:8000/agent \\
                 -H "Content-Type: application/json" \\
                 -d \'{{"task": "find me study time this week"}}\'
        """

        import sys, json
        sys.path.insert(0, "context-mcp")

        from fastapi import FastAPI
        from pydantic import BaseModel
        from anthropic import Anthropic

        from context_engine import {imports}

        client = Anthropic()
        app    = FastAPI(title="{name}")

        SYSTEM_PROMPT = """{prompt}"""

        class Request(BaseModel):
            task: str

        @app.post("/agent")
        def run_agent(req: Request):
            {ctx_lines}

            response = client.messages.create(
                model="{model}",
                max_tokens=1000,
                system=SYSTEM_PROMPT + f"\\n\\nPersonal context:\\n{{json.dumps(ctx, indent=2)}}",
                messages=[{{"role": "user", "content": req.task}}],
            )
            return {{
                "response": response.content[0].text,
                "context_used": ctx,
            }}

        if __name__ == "__main__":
            import uvicorn
            uvicorn.run(app, host="0.0.0.0", port=8000)
    ''')


def generate_raw(cfg: dict) -> str:
    selected  = [k for k, v in cfg["tools"].items() if v]
    imports   = ", ".join(TOOL_DEFS[k]["import"] for k in selected) or "get_context"
    ctx_lines = "\n    ".join(
        TOOL_DEFS[k]["raw_call"] for k in selected if TOOL_DEFS[k]["raw_call"]
    ) or "ctx = {}"
    name  = cfg["name"] or "PersonalContextAgent"
    model = cfg["model"]
    prompt = cfg["system_prompt"].replace('"""', "'''")

    return textwrap.dedent(f'''\
        """
        {name} — PersonalContext Agent
        Framework : Raw Python (no server)
        Generated : PersonalContext Builder

        Run:
            python agent.py
        """

        import sys, json
        sys.path.insert(0, "context-mcp")

        from anthropic import Anthropic
        from context_engine import {imports}

        client = Anthropic()

        SYSTEM_PROMPT = """{prompt}"""

        def run(task: str) -> str:
            {ctx_lines}

            response = client.messages.create(
                model="{model}",
                max_tokens=1000,
                system=SYSTEM_PROMPT + f"\\n\\nPersonal context:\\n{{json.dumps(ctx, indent=2)}}",
                messages=[{{"role": "user", "content": task}}],
            )
            return response.content[0].text

        if __name__ == "__main__":
            task = input("Task: ")
            print("\\n" + run(task))
    ''')


def requirements_txt(framework: str) -> str:
    base = "anthropic>=0.95\npython-dotenv>=1.2\nchromadb>=0.6.0\nsentence-transformers>=3.0\n"
    if framework == "LangChain + LangServe":
        return base + "langchain-anthropic\nlangchain-core\nlanggraph\nlangserve[all]\nfastapi\nuvicorn\n"
    if framework == "FastAPI":
        return base + "fastapi\nuvicorn\n"
    return base


def dockerfile(framework: str) -> str:
    cmd = "uvicorn agent_server:app --host 0.0.0.0 --port 8000" if framework != "Raw Python" else "python agent.py"
    fname = "agent_server.py" if framework != "Raw Python" else "agent.py"
    return textwrap.dedent(f"""\
        FROM python:3.13-slim
        WORKDIR /app
        COPY . .
        RUN pip install --no-cache-dir -r requirements.txt
        EXPOSE 8000
        CMD ["{cmd.split()[0]}", {', '.join(f'"{p}"' for p in cmd.split()[1:])}]
    """)


def make_zip(agent_code: str, req: str, dock: str, framework: str) -> bytes:
    buf   = io.BytesIO()
    fname = "agent_server.py" if framework != "Raw Python" else "agent.py"

    if "LangChain" in framework:
        run_cmd      = "uvicorn agent_server:app --reload --port 8000"
        test_section = (
            "## Test\n"
            "```bash\n"
            "curl -X POST http://localhost:8000/agent/invoke \\\n"
            '     -H "Content-Type: application/json" \\\n'
            '     -d \'{"input": {"messages": [{"type": "human", "content": "your task"}]}}\'\n'
            "```\n"
        )
    elif framework == "FastAPI":
        run_cmd      = "uvicorn agent_server:app --reload --port 8000"
        test_section = (
            "## Test\n"
            "```bash\n"
            "curl -X POST http://localhost:8000/agent \\\n"
            '     -H "Content-Type: application/json" \\\n'
            '     -d \'{"task": "your task here"}\'\n'
            "```\n"
        )
    else:
        run_cmd      = "python " + fname
        test_section = ""

    readme = (
        "# " + fname.split(".")[0] + "\n\n"
        "Generated by PersonalContext Builder.\n\n"
        "## Setup\n"
        "```bash\n"
        "cp .env.example .env\n"
        "pip install -r requirements.txt\n"
        "```\n\n"
        "## Run\n"
        "```bash\n"
        + run_cmd + "\n"
        + "```\n\n"
        + test_section
    )

    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(fname, agent_code)
        zf.writestr("requirements.txt", req)
        zf.writestr("Dockerfile", dock)
        zf.writestr(".env.example", "ANTHROPIC_API_KEY=sk-ant-...")
        zf.writestr("README.md", readme)
    buf.seek(0)
    return buf.getvalue()


def run_test(task: str, cfg: dict) -> tuple[str, str, dict]:
    """Run naive and enhanced agents with the user's config. Returns (naive, enhanced, ctx)."""
    has_context = cfg["tools"].get("get_personal_context", False)

    def _naive():
        r = client.messages.create(
            model=cfg["model"],
            max_tokens=600,
            system=cfg["system_prompt"] or "You are a helpful assistant.",
            messages=[{"role": "user", "content": task}],
        )
        return r.content[0].text

    def _enhanced():
        ctx = get_context(task) if has_context else {}
        system = cfg["system_prompt"] or "You are a helpful assistant."
        if ctx:
            system += f"\n\nPersonal context:\n{json.dumps(ctx, indent=2)}"
        r = client.messages.create(
            model=cfg["model"],
            max_tokens=600,
            system=system,
            messages=[{"role": "user", "content": task}],
        )
        return r.content[0].text, ctx

    with ThreadPoolExecutor(max_workers=2) as pool:
        naive_f    = pool.submit(_naive)
        enhanced_f = pool.submit(_enhanced)
        naive_r    = naive_f.result()
        enhanced_r, ctx = enhanced_f.result()

    return naive_r, enhanced_r, ctx


# ── Header ─────────────────────────────────────────────────────────────────────

st.markdown("# ⚙️ Agent Builder")
st.markdown(
    "Configure a PersonalContext-powered agent. Test it live. "
    "Export deployment-ready code."
)
st.divider()

# ── Layout: config (left) | preview (right) ───────────────────────────────────

col_cfg, col_preview = st.columns([2, 3], gap="large")

# ══════════════════════════════════════════════════════════════════════════════
# LEFT — Configuration
# ══════════════════════════════════════════════════════════════════════════════

with col_cfg:
    st.markdown("### Agent name")
    agent_name = st.text_input(
        "Name",
        value="My PersonalContext Agent",
        label_visibility="collapsed",
    )

    st.markdown("")
    st.markdown("### System prompt")

    preset = st.selectbox(
        "Load a preset",
        list(SYSTEM_PROMPT_PRESETS.keys()),
        label_visibility="collapsed",
    )
    default_prompt = SYSTEM_PROMPT_PRESETS[preset]

    system_prompt = st.text_area(
        "System prompt",
        value=default_prompt,
        height=180,
        label_visibility="collapsed",
        placeholder="Describe what your agent should do...",
    )

    st.markdown("")
    st.markdown("### PersonalContext tools")
    st.caption("Which tools should your agent have access to?")

    tool_get_ctx  = st.checkbox("get_personal_context — task-aware context retrieval", value=True)
    tool_profile  = st.checkbox("get_user_profile — behavioral profile & preferences", value=False)
    tool_search   = st.checkbox("search_personal_memory — semantic search over data", value=False)

    st.markdown("")
    st.markdown("### Model")
    model_key = st.selectbox(
        "Model",
        list(MODELS.keys()),
        format_func=lambda k: MODELS[k],
        label_visibility="collapsed",
    )

    st.markdown("")
    st.markdown("### Framework")
    framework = st.radio(
        "Framework",
        ["LangChain + LangServe", "FastAPI", "Raw Python"],
        label_visibility="collapsed",
        horizontal=True,
    )

    # Build config dict
    cfg = {
        "name":          agent_name,
        "system_prompt": system_prompt,
        "model":         model_key,
        "framework":     framework,
        "tools": {
            "get_personal_context": tool_get_ctx,
            "get_user_profile":     tool_profile,
            "search_memory":        tool_search,
        },
    }

    active_tools = [TOOL_DEFS[k]["label"] for k, v in cfg["tools"].items() if v]
    if active_tools:
        st.caption("Active: " + " · ".join(f"`{t}`" for t in active_tools))

# ══════════════════════════════════════════════════════════════════════════════
# RIGHT — Preview tabs
# ══════════════════════════════════════════════════════════════════════════════

with col_preview:
    tab_test, tab_code, tab_deploy = st.tabs(["▶  Test", "{ } Code", "🚀  Deploy"])

    # ── Test tab ──────────────────────────────────────────────────────────────

    with tab_test:
        st.markdown("### Test your agent")
        st.caption(
            "Runs your configured agent live against your personal data. "
            "Left: without context tools. Right: with them."
        )

        task_input = st.text_input(
            "Task",
            placeholder="e.g. Find me a 2-hour study block for CS231N this week",
            label_visibility="collapsed",
        )

        run_btn = st.button("▶  Run", type="primary", disabled=not task_input)

        if run_btn and task_input:
            with st.spinner("Running agents in parallel…"):
                naive_r, enhanced_r, ctx = run_test(task_input, cfg)

            c1, c2 = st.columns(2)

            with c1:
                st.markdown(
                    '<div class="resp-panel resp-naive">'
                    '<div class="resp-label" style="color:#804040">WITHOUT CONTEXT TOOLS</div>'
                    f'<div class="resp-body">{naive_r}</div>'
                    '</div>',
                    unsafe_allow_html=True,
                )

            with c2:
                st.markdown(
                    '<div class="resp-panel resp-enhanced">'
                    '<div class="resp-label" style="color:#408060">WITH PERSONALCONTEXT</div>'
                    f'<div class="resp-body">{enhanced_r}</div>'
                    '</div>',
                    unsafe_allow_html=True,
                )

            if ctx:
                st.markdown("")
                st.markdown("**What the context layer retrieved**")
                col_a, col_b = st.columns(2)
                with col_a:
                    user = ctx.get("user", {})
                    if user.get("work_style"):
                        st.markdown(f"- **Work style:** {user['work_style']}")
                    if user.get("peak_focus_hours"):
                        st.markdown(f"- **Peak focus:** {', '.join(user['peak_focus_hours'])}")
                    for d in ctx.get("deadlines", [])[:3]:
                        dot = {"high":"🔴","medium":"🟡","low":"🟢"}.get(d.get("urgency",""),"⚪")
                        st.markdown(f"- {dot} **{d.get('course','')}** {d.get('assignment','')} — {d.get('due_date','')}")
                with col_b:
                    for b in ctx.get("schedule", {}).get("free_blocks", [])[:4]:
                        st.markdown(f"- 🕐 {b}")
                    for m in ctx.get("relevant_memories", [])[:3]:
                        src_icon = {"gmail":"📧","gcal":"📅","canvas":"📚"}.get(m.get("source",""),"📄")
                        st.markdown(f"- {src_icon} *{m.get('why_relevant','')}*")

                with st.expander("Full PersonalContext object", expanded=False):
                    st.json(ctx)

        elif not task_input:
            st.caption("Enter a task above to test your agent.")

    # ── Code tab ──────────────────────────────────────────────────────────────

    with tab_code:
        st.markdown("### Generated code")
        st.caption("Updates live as you change the configuration. Copy or download.")

        if framework == "LangChain + LangServe":
            agent_code = generate_langchain(cfg)
            fname = "agent_server.py"
        elif framework == "FastAPI":
            agent_code = generate_fastapi(cfg)
            fname = "agent_server.py"
        else:
            agent_code = generate_raw(cfg)
            fname = "agent.py"

        st.code(agent_code, language="python")

        st.download_button(
            f"⬇  Download {fname}",
            data=agent_code,
            file_name=fname,
            mime="text/plain",
        )

    # ── Deploy tab ─────────────────────────────────────────────────────────────

    with tab_deploy:
        st.markdown("### Deploy your agent")

        req  = requirements_txt(framework)
        dock = dockerfile(framework)

        if framework != "Raw Python":
            st.markdown("**1. Install dependencies**")
            st.code(f"pip install -r requirements.txt", language="bash")

            st.markdown("**2. Set your API key**")
            st.code("export ANTHROPIC_API_KEY=sk-ant-...", language="bash")

            st.markdown("**3. Run the server**")
            if framework == "LangChain + LangServe":
                st.code("uvicorn agent_server:app --reload --port 8000", language="bash")
                st.markdown("**4. Test the endpoint**")
                st.code(
                    'curl -X POST http://localhost:8000/agent/invoke \\\n'
                    '     -H "Content-Type: application/json" \\\n'
                    '     -d \'{"input": {"messages": [{"type": "human", "content": "find me study time"}]}}\'',
                    language="bash",
                )
            else:
                st.code("uvicorn agent_server:app --reload --port 8000", language="bash")
                st.markdown("**4. Test the endpoint**")
                st.code(
                    'curl -X POST http://localhost:8000/agent \\\n'
                    '     -H "Content-Type: application/json" \\\n'
                    '     -d \'{"task": "find me study time this week"}\'',
                    language="bash",
                )
        else:
            st.markdown("**1. Install dependencies**")
            st.code("pip install -r requirements.txt", language="bash")
            st.markdown("**2. Run**")
            st.code("python agent.py", language="bash")

        st.divider()

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**requirements.txt**")
            st.code(req, language="text")
        with c2:
            st.markdown("**Dockerfile**")
            st.code(dock, language="dockerfile")

        st.markdown("")

        if framework != "Raw Python":
            st.markdown(
                "**Docker deploy**  \n"
                "```bash\n"
                "docker build -t my-agent .\n"
                "docker run -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY -p 8000:8000 my-agent\n"
                "```"
            )

        st.markdown("")
        zip_bytes = make_zip(agent_code, req, dock, framework)
        st.download_button(
            "⬇  Download all files (.zip)",
            data=zip_bytes,
            file_name=f"{agent_name.lower().replace(' ', '_')}.zip",
            mime="application/zip",
        )
