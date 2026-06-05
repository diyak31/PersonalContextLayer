"""
PersonalContext — Product Demo

Home page + Demo tab.
Run with:  streamlit run demo/app.py
"""

import re
import sys
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent / "context-mcp"))
sys.path.insert(0, str(Path(__file__).parent))

from agents import naive_agent, enhanced_agent_with_context, explain_response, get_agents
from context_engine import get_context, get_last_updated, refresh, _get_collection, _get_profile

# ── Context layer — cached once ────────────────────────────────────────────────

@st.cache_resource(show_spinner="Initializing context layer…")
def init_context_layer() -> dict:
    col     = _get_collection()
    profile = _get_profile()
    total   = col.count()
    by_source = {}
    for src in ["gmail", "gcal", "canvas", "course_websites", "purchases"]:
        try:
            count = len(col.get(where={"source": src})["ids"])
            if count:
                by_source[src] = count
        except Exception:
            pass
    return {
        "vectors":    total,
        "sources":    by_source,
        "work_style": profile.get("summary", {}).get("work_style", ""),
        "peak_hours": profile.get("summary", {}).get("peak_activity_hours", []),
        "courses":    profile.get("academics", {}).get("courses", []),
    }


# ── Page config ────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="PersonalContext",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
  /* ── Reset & base ── */
  .stApp { background: #0e0e18; }
  section[data-testid="stSidebar"] { display: none; }
  * { font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", sans-serif; }
  p, li, .stMarkdown { color: #8080b8; font-size: 0.9rem; line-height: 1.7; }
  hr { border-color: #1a1a2e !important; }

  /* ── Tabs ── */
  .stTabs [data-baseweb="tab-list"] {
    background: transparent;
    border-bottom: 1px solid #1a1a2e;
    gap: 0; padding: 0;
  }
  .stTabs [data-baseweb="tab"] {
    background: transparent; color: #6060a0;
    border-radius: 0; font-size: 0.85rem;
    font-weight: 500; padding: 12px 20px;
    border-bottom: 2px solid transparent;
  }
  .stTabs [aria-selected="true"] {
    background: transparent !important;
    color: #94f0f1 !important;
    border-bottom: 2px solid #8bf0ba !important;
  }

  /* ── Hero ── */
  .hero {
    background: radial-gradient(ellipse 80% 55% at 50% -5%,
      rgba(14,15,237,.18) 0%, rgba(148,240,241,.06) 50%, transparent 70%);
    border-bottom: 1px solid #1a1a2e;
    padding: 72px 0 52px;
    text-align: center;
  }
  .hero-eyebrow {
    display: inline-flex; align-items: center; gap: 6px;
    background: rgba(14,15,237,.12); border: 1px solid rgba(14,15,237,.35);
    border-radius: 20px; padding: 4px 14px;
    font-size: 0.72rem; font-weight: 600; color: #6a6aff;
    letter-spacing: 0.06em; text-transform: uppercase;
    margin-bottom: 24px;
  }
  .hero-title {
    font-size: clamp(2rem, 5vw, 3.2rem); font-weight: 700;
    color: #94f0f1; line-height: 1.15; letter-spacing: -0.03em;
    margin: 0 auto 16px; max-width: 640px;
  }
  .hero-sub {
    font-size: 1.05rem; color: #7070b0;
    max-width: 480px; margin: 0 auto 36px;
    line-height: 1.6;
  }
  .live-badge {
    display: inline-flex; align-items: center; gap: 8px;
    border: 1px solid #1a1a2e; background: rgba(14,15,237,.08); border-radius: 8px;
    padding: 8px 18px; margin-top: 32px;
    font-size: 0.8rem; color: #7070b0;
  }
  .live-dot {
    width: 7px; height: 7px; border-radius: 50%;
    background: #8bf0ba; flex-shrink: 0;
  }

  /* ── Feature cards ── */
  .feat-grid { display: flex; gap: 16px; margin: 48px 0 24px; }
  .feat-card {
    flex: 1; background: #0e0e18;
    border: 1px solid #1a1a2e; border-radius: 12px;
    padding: 24px;
  }
  .feat-icon {
    width: 36px; height: 36px; border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1rem; margin-bottom: 14px;
  }
  .feat-icon.structured { background: rgba(114,225,209,.12); }
  .feat-icon.behavioral { background: rgba(141,59,114,.12); }
  .feat-icon.semantic   { background: rgba(138,112,144,.12); }
  .feat-title { font-size: 0.95rem; font-weight: 600; color: #94f0f1; margin-bottom: 6px; }
  .feat-desc  { font-size: 0.82rem; color: #7070b0; line-height: 1.5; }
  .feat-items { margin-top: 12px; }
  .feat-item  {
    font-size: 0.78rem; color: #8080b8; padding: 4px 0;
    border-top: 1px solid #1a1a2e;
    display: flex; align-items: center; gap: 8px;
  }
  .feat-dot { width: 4px; height: 4px; border-radius: 50%; flex-shrink: 0; }

  /* ── How it works ── */
  .steps { display: flex; gap: 0; margin: 12px 0; }
  .step {
    flex: 1; padding: 24px 28px;
    background:#0e0e18; border: 1px solid #1a1a2e; border-right: none;
  }
  .step:first-child { border-radius: 8px 0 0 8px; }
  .step:last-child  { border-right: 1px solid #1a1a2e; border-radius: 0 8px 8px 0; }
  .step-num {
    font-size: 0.65rem; font-weight: 700; color: #8bf0ba;
    text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 10px;
  }
  .step-title { font-size: 0.95rem; font-weight: 600; color: #94f0f1; margin-bottom: 6px; }
  .step-desc  { font-size: 0.8rem; color: #7070b0; line-height: 1.5; }
  .step-code  {
    font-family: "SF Mono","Fira Code",monospace;
    font-size: 0.78rem; color: #8bf0ba;
    background: rgba(114,225,209,.15); border-radius: 4px;
    padding: 6px 10px; margin-top: 10px;
    border: 1px solid rgba(114,225,209,.15);
  }

  /* ── Section label ── */
  .section-label {
    font-size: 0.65rem; font-weight: 600; color: #8080b8;
    text-transform: uppercase; letter-spacing: 0.12em;
    margin-bottom: 16px;
  }

  /* ── Demo: diff bar ── */
  .diff-bar {
    display: flex; border: 1px solid #1a1a2e; background: #0e0e18;
    border-radius: 8px; overflow: hidden; margin: 20px 0;
  }
  .diff-metric { flex: 1; padding: 16px; text-align: center; border-right: 1px solid #1a1a2e; }
  .diff-metric:last-child { border-right: none; }
  .diff-metric .val { font-size: 1.3rem; font-weight: 600; color: #94f0f1; letter-spacing: -0.02em; }
  .diff-metric .lbl { font-size: 0.62rem; color: #8080b8; text-transform: uppercase;
                      letter-spacing: 0.1em; margin-top: 4px; }
  .diff-metric .delta { font-size: 0.72rem; margin-top: 3px; font-weight: 500; }
  .diff-metric .delta.pos { color: #8bf0ba; }
  .diff-metric .delta.neg { color: #f2b1d8; }

  /* ── Demo: memory cards ── */
  .mem-card {
    background: #0e0e18; border: 1px solid #1a1a2e; border-radius: 6px;
    padding: 12px 14px; margin-bottom: 8px;
  }
  .mem-card.structured { border-left: 2px solid #8bf0ba; }
  .mem-card.behavioral { border-left: 2px solid #f2b1d8; }
  .mem-card.semantic   { border-left: 2px solid #94f0f1; }
  .mem-type-label {
    font-size: 0.62rem; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.1em; color: #8080b8; margin-bottom: 8px;
  }
  .conf-bar  { height: 2px; background: #1a1a2e; border-radius: 1px; margin: 6px 0 4px; }
  .conf-fill { height: 2px; background: #8bf0ba; border-radius: 1px; }
  .src-tag {
    display: inline-block; border: 1px solid #1a1a2e; background:#141420; border-radius: 3px;
    padding: 1px 5px; font-size: 0.65rem; color: #8080b8;
    font-family: "SF Mono","Fira Code",monospace; margin-right: 4px;
  }

  /* ── Demo: trace ── */
  .trace-claim {
    background:#0e0e18; border: 1px solid #1a1a2e; border-radius: 6px;
    padding: 10px 12px; margin: 5px 0;
  }
  .trace-claim .claim-text { color: #94f0f1; font-size: 0.84rem; margin-bottom: 4px; }
  .trace-evidence { color: #8080b8; font-size: 0.75rem; }
  .trace-generic {
    background:#fff; border: 1px solid #1a1a2e; border-left: 2px solid #1a1a2e;
    border-radius: 6px; padding: 8px 12px; margin: 4px 0;
    color: #7070a0; font-size: 0.78rem;
  }
  .pscore { font-size: 1.6rem; font-weight: 600; color: #8bf0ba; }

  /* ── Buttons — all variants ── */
  .stButton button {
    background: #0e0e18 !important;
    border: 1px solid #1a1a2e !important;
    color: #404060 !important;
    border-radius: 6px !important;
    font-size: 0.82rem !important;
    transition: all 0.15s !important;
  }
  .stButton button:hover {
    background: #0e0e18 !important;
    border-color: #8bf0ba !important;
    color: #8bf0ba !important;
  }
  .stButton button[kind="primary"],
  button[kind="primary"] {
    background: #8bf0ba !important;
    border: none !important;
    color: #fff !important;
    font-weight: 500 !important;
  }
  .stButton button[kind="primary"]:hover,
  button[kind="primary"]:hover {
    background: #7a3364 !important;
    color: #fff !important;
  }

  /* ── All Streamlit containers ── */
  [data-testid="stAppViewContainer"],
  [data-testid="stHeader"],
  [data-testid="stToolbar"],
  .block-container,
  [data-testid="stVerticalBlock"] { background: transparent !important; }
  [data-testid="stHeader"] { border-bottom: 1px solid #1a1a2e !important; }

  /* ── Text inputs & selects ── */
  .stTextInput > div > div > input,
  .stTextInput input {
    background: #0e0e18 !important; border: 1px solid #1a1a2e !important;
    color: #94f0f1 !important; border-radius: 6px !important;
  }
  .stTextInput label, .stSelectbox label {
    color: #404060 !important; font-size: 0.82rem !important;
  }
  .stSelectbox [data-baseweb="select"] > div,
  .stSelectbox div[data-baseweb="select"] > div {
    background: #0e0e18 !important; border: 1px solid #1a1a2e !important;
    border-radius: 6px !important; color: #94f0f1 !important;
  }
  [data-baseweb="popover"] [data-baseweb="menu"] {
    background: #0e0e18 !important; border: 1px solid #1a1a2e !important;
  }
  [data-baseweb="option"]:hover { background: #0e0e18 !important; }

  /* ── Info / alert boxes ── */
  [data-testid="stAlert"],
  .stAlert {
    background: rgba(14,15,237,.08) !important;
    border: 1px solid #1a1a2e !important;
    border-radius: 6px !important; color: #404060 !important;
  }
  [data-testid="stAlert"] p,
  .stAlert p { color: #404060 !important; }
  /* Override the blue icon on info boxes */
  [data-testid="stAlert"] svg { color: #8bf0ba !important; fill: #8bf0ba !important; }

  /* ── Captions ── */
  .stCaption, [data-testid="stCaptionContainer"] p {
    color: #7070a0 !important;
  }

  /* ── Expanders ── */
  [data-testid="stExpander"] {
    background: #0e0e18 !important;
    border: 1px solid #1a1a2e !important;
    border-radius: 8px !important;
  }
  [data-testid="stExpander"] summary {
    color: #404060 !important;
  }
  [data-testid="stExpander"] summary:hover {
    color: #8bf0ba !important;
  }
  .streamlit-expanderHeader {
    background: #0e0e18 !important; color: #404060 !important;
  }

  /* ── Code blocks ── */
  .stCode, [data-testid="stCode"],
  pre, code {
    background: #0a0a16 !important;
    border: 1px solid #1a1a2e !important;
    border-radius: 6px !important;
    color: #c8d8ff !important;
  }
  /* ── Syntax token colors (IDE-style) ── */

  /* Comments — dim */
  .highlight .c, .highlight .c1, .highlight .cm, .highlight .cs,
  pre .c, pre .c1, pre .cm, pre .cs { color: #4a5070 !important; font-style: italic; }

  /* Keywords: from, import, await, def, class, return */
  .highlight .k, .highlight .kn, .highlight .kd, .highlight .kw, .highlight .kr,
  pre .k, pre .kn, pre .kd, pre .kw { color: #94f0f1 !important; }

  /* Strings */
  .highlight .s, .highlight .s1, .highlight .s2, .highlight .sb,
  .highlight .se, .highlight .si, .highlight .sh,
  pre .s, pre .s1, pre .s2, pre .sb { color: #f2b1d8 !important; }

  /* Function names */
  .highlight .nf, .highlight .fm,
  pre .nf, pre .fm { color: #ffdc6a !important; }

  /* Built-ins */
  .highlight .nb, pre .nb { color: #ffdc6a !important; }

  /* Class / namespace names */
  .highlight .nn, .highlight .nc,
  pre .nn, pre .nc { color: #8bf0ba !important; }

  /* Operators: =, ==, +, etc. */
  .highlight .o, .highlight .ow,
  pre .o, pre .ow { color: #8bf0ba !important; }

  /* Numbers */
  .highlight .mi, .highlight .mf, .highlight .mo,
  pre .mi, pre .mf { color: #ffdc6a !important; }

  /* Default names, identifiers, punctuation */
  .highlight .n, .highlight .na, .highlight .ni, .highlight .p,
  pre .n, pre .na, pre .p { color: #c8d8ff !important; }

  /* Decorators */
  .highlight .nd, pre .nd { color: #f2b1d8 !important; }

  /* ── JSON viewer ── */
  [data-testid="stJson"] {
    background: #0e0e18 !important;
    border: 1px solid #1a1a2e !important;
    border-radius: 6px !important;
  }

  /* ── Markdown headings ── */
  h1, h2, h3, h4, h5 { color: #94f0f1 !important; }

  /* ── Spinner / loading ── */
  [data-testid="stSpinner"] > div,
  .stSpinner > div {
    border-color: #1a1a2e transparent transparent transparent !important;
    border-top-color: #8bf0ba !important;
  }
  [data-testid="stStatusWidget"] {
    background: #0e0e18 !important;
    border: 1px solid #1a1a2e !important;
    border-radius: 8px !important;
    color: #404060 !important;
  }
  [data-testid="stStatusWidget"] label { color: #404060 !important; }

  /* ── App loading overlay (cache_resource spinner) ── */
  [data-testid="stAppViewBlockContainer"] { background: #0e0e18 !important; }
  .element-container .stSpinner { background: #0e0e18; }

  /* ── Divider ── */
  [data-testid="stDivider"] { border-color: #1a1a2e !important; }

  /* ── Footer ── */
  footer { display: none !important; }
  [data-testid="stDecoration"] { display: none !important; }
</style>
""", unsafe_allow_html=True)

# ── Helpers ────────────────────────────────────────────────────────────────────

SOURCE_LABEL  = {"gmail":"gmail","gcal":"calendar","canvas":"canvas",
                 "course_websites":"courses","purchases":"purchases","behavioral":"behavioral"}
URGENCY_COLOR = {"high":"#7070a0","medium":"#7070a0","low":"#8bf0ba"}
PLATFORMS     = {
    "LangChain":   "🦜 LangChain",
    "CrewAI":      "🤝 CrewAI",
    "LlamaIndex":  "🦙 LlamaIndex",
    "Raw MCP":     "🔌 Raw MCP",
    "Custom agent":"⚙️  Custom",
}
EXAMPLE_PROMPTS = [
    "Find me a 2-hour study block for CS231N this week",
    "Draft an email to my professor asking for a deadline extension",
    "What should I prioritize this week given my deadlines?",
    "Who do I email most and what do we talk about?",
    "What have I been spending money on lately?",
    "When am I least busy this week?",
]


def count_specifics(text: str) -> int:
    patterns = [
        r'\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b',
        r'\b\d{1,2}:\d{2}\s*(am|pm|AM|PM)?\b',
        r'\bCS\s*\d{3}[A-Z]?\b',
        r'\$\d+',
        r'\b\d+\s*(days?|hours?|weeks?)\b',
    ]
    return sum(len(re.findall(p, text, re.IGNORECASE)) for p in patterns)


def count_actionable(text: str) -> int:
    return len(re.findall(r'(?m)^[\s]*[-•*]|^\s*\d+\.', text))


def _src_tag(source: str) -> str:
    return f'<span class="src-tag">{SOURCE_LABEL.get(source, source)}</span>'


def render_diff_bar(naive: str, enhanced: str, ctx: dict):
    n_spec = count_specifics(naive)
    e_spec = count_specifics(enhanced)
    n_act  = count_actionable(naive)
    e_act  = count_actionable(enhanced)
    e_mem  = len(ctx.get("semantic", {}).get("memories", []))
    n_asks = any(p in naive.lower() for p in
                 ["could you","can you tell","what is your","please share","let me know","when is"])
    e_asks = any(p in enhanced.lower() for p in
                 ["could you","can you tell","what is your","please share","let me know","when is"])
    spec_d = e_spec - n_spec
    act_d  = e_act  - n_act

    def m(val, lbl, delta, cls="pos"):
        return (f'<div class="diff-metric"><div class="val">{val}</div>'
                f'<div class="lbl">{lbl}</div>'
                f'<div class="delta {cls}">{delta}</div></div>')

    st.markdown(
        '<div class="diff-bar">'
        + m(f"{n_spec} → {e_spec}", "specificity",
            f"+{spec_d} entities" if spec_d >= 0 else f"{spec_d}",
            "pos" if spec_d > 0 else "neg")
        + m(f"{n_act} → {e_act}", "concrete suggestions",
            f"+{act_d}" if act_d >= 0 else str(act_d),
            "pos" if act_d > 0 else "neg")
        + m(str(e_mem), "memories used", "from your data")
        + m("no" if not e_asks else "yes",
            "asked for clarification",
            "answered directly" if not e_asks else "fallback triggered",
            "pos" if not e_asks else "neg")
        + '</div>',
        unsafe_allow_html=True,
    )


def render_context_panel(ctx: dict):
    summary = ctx.get("task_summary", "")
    if summary:
        st.markdown(f'<p style="color:#7070a0;font-size:0.8rem;margin-bottom:12px">{summary}</p>',
                    unsafe_allow_html=True)

    structured = ctx.get("structured", {})
    deadlines  = structured.get("deadlines", [])
    free       = structured.get("schedule", {}).get("free_blocks", [])

    if deadlines or free:
        rows = ""
        for d in deadlines[:3]:
            c = URGENCY_COLOR.get(d.get("urgency",""), "#404060")
            rows += (f'<div style="display:flex;align-items:center;gap:8px;padding:5px 0;'
                     f'border-bottom:1px solid #0e0e18;font-size:0.8rem">'
                     f'<span style="width:5px;height:5px;border-radius:50%;background:{c};flex-shrink:0"></span>'
                     f'<span style="color:#94f0f1">{d.get("course","")} — {d.get("assignment","")}</span>'
                     f'<span style="margin-left:auto;color:#7070a0;font-size:0.72rem">{d.get("due_date","")}</span>'
                     f'</div>')
        for b in free[:3]:
            rows += (f'<div style="padding:5px 0;border-bottom:1px solid #0e0e18;'
                     f'font-size:0.8rem;color:#404060">{b}</div>')
        st.markdown(f'<div class="mem-card structured"><div class="mem-type-label">Structured</div>{rows}</div>',
                    unsafe_allow_html=True)

    behavioral = ctx.get("behavioral", {})
    if behavioral.get("work_style"):
        conf  = behavioral.get("confidence", 0)
        hours = ", ".join(behavioral.get("peak_focus_hours", []))
        inferred = behavioral.get("inferred_from", "")
        traits = "".join(f'<div style="font-size:0.76rem;color:#404060;padding:2px 0">{t}</div>'
                         for t in behavioral.get("relevant_traits", [])[:2])
        st.markdown(
            f'<div class="mem-card behavioral"><div class="mem-type-label">Behavioral</div>'
            f'<div style="font-size:0.86rem;color:#94f0f1;margin-bottom:6px">{behavioral["work_style"]} · peak {hours}</div>'
            f'<div class="conf-bar"><div class="conf-fill" style="width:{int(conf*100)}%"></div></div>'
            f'<div style="font-size:0.68rem;color:#7070a0;margin-bottom:6px">{conf:.0%} confidence · {inferred}</div>'
            f'{traits}</div>',
            unsafe_allow_html=True,
        )

    semantic = ctx.get("semantic", {})
    memories = semantic.get("memories", [])
    tags     = semantic.get("identity_tags", [])
    active   = semantic.get("active_context", "")

    if memories or tags:
        tags_html   = "".join(f'<span class="src-tag">{t}</span>' for t in tags)
        active_html = f'<div style="font-size:0.72rem;color:#7070a0;margin:5px 0">{active}</div>' if active else ""
        mems_html   = ""
        for m in memories[:4]:
            conf = m.get("confidence", m.get("relevance", 0))
            mems_html += (f'<div style="padding:5px 0;border-bottom:1px solid #0e0e18;font-size:0.78rem">'
                          f'{_src_tag(m.get("source",""))}'
                          f'<span style="color:#404060">{m.get("why_relevant","")}</span>'
                          f'<span style="float:right;color:#1a1a2e;font-size:0.68rem">{conf:.0%}</span></div>')
        st.markdown(f'<div class="mem-card semantic"><div class="mem-type-label">Semantic</div>'
                    f'{tags_html}{active_html}{mems_html}</div>',
                    unsafe_allow_html=True)

    note = ctx.get("agent_note", "")
    if note:
        st.markdown(f'<p style="color:#7070a0;font-size:0.72rem;margin-top:8px">{note}</p>',
                    unsafe_allow_html=True)


def render_explain(task: str, response: str, ctx: dict, key: str):
    if st.button("Trace this response →", key=f"explain_{key}"):
        with st.spinner("Tracing…"):
            try:
                st.session_state[f"trace_{key}"] = explain_response(task, response, ctx)
            except Exception as e:
                st.error(str(e))

    trace = st.session_state.get(f"trace_{key}")
    if not trace:
        return

    score = trace.get("personalization_score", 0)
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:10px;margin:10px 0">'
        f'<span class="pscore">{score:.0%}</span>'
        f'<span style="color:#404060;font-size:0.82rem">{trace.get("summary","")}</span>'
        f'</div>', unsafe_allow_html=True)

    for c in trace.get("grounded_claims", []):
        conf = c.get("confidence", 0)
        st.markdown(
            f'<div class="trace-claim">'
            f'<div class="claim-text">"{c.get("claim","")}"</div>'
            f'{_src_tag(c.get("source_name",""))}'
            f'<span class="trace-evidence">{c.get("evidence","")}</span>'
            f'<span style="float:right;color:#1a1a2e;font-size:0.68rem">{conf:.0%}</span>'
            f'</div>', unsafe_allow_html=True)

    for c in trace.get("generic_claims", []):
        st.markdown(
            f'<div class="trace-generic">"{c.get("claim","")}"'
            f'<span style="color:#7070a0"> — {c.get("note","")}</span></div>',
            unsafe_allow_html=True)


# ── Init ───────────────────────────────────────────────────────────────────────

layer = init_context_layer()

# ── Tabs ───────────────────────────────────────────────────────────────────────

tab_home, tab_demo, tab_setup = st.tabs(["Home", "Demo", "Setup"])


# ══════════════════════════════════════════════════════════════════════════════
# HOME
# ══════════════════════════════════════════════════════════════════════════════

with tab_home:

    # ── Hero ──────────────────────────────────────────────────────────────────
    sources_str = "  ·  ".join(layer["sources"].keys())

    st.markdown(f"""
    <div class="hero">
      <div class="hero-eyebrow">
        <span style="width:6px;height:6px;background:#8bf0ba;border-radius:50%;display:inline-block"></span>
        Memory infrastructure for AI agents
      </div>
      <div class="hero-title">The memory system<br>for AI agents.</div>
      <div class="hero-sub">
        One call. Any agent framework. Full personal context —
        structured, behavioral, and semantic.
      </div>
      <div class="live-badge">
        <span class="live-dot"></span>
        <span><b style="color:#8bf0ba">{layer["vectors"]:,} vectors</b>&nbsp; live now &nbsp;·&nbsp; {sources_str}</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Freshness indicator + refresh ─────────────────────────────────────────
    freshness = get_last_updated()
    stale_sources = [s for s, v in freshness.items() if v["stale"] and s != "gcal"]

    age_parts = []
    for src, info in freshness.items():
        color = "#8bf0ba" if not info["stale"] else "#ffdc6a" if info["age"] != "never" else "#f2b1d8"
        age_parts.append(
            f'<span style="font-size:0.72rem;color:{color};margin-right:12px">'
            f'<span style="opacity:0.6">{src}</span> {info["age"]}</span>'
        )

    refresh_col, status_col = st.columns([1, 4])
    with status_col:
        st.markdown(
            '<div style="display:flex;align-items:center;flex-wrap:wrap;padding:6px 0">'
            + "".join(age_parts)
            + "</div>",
            unsafe_allow_html=True,
        )
    with refresh_col:
        if st.button("↻ Refresh now", key="hero_refresh"):
            with st.spinner("Re-ingesting recent data…"):
                results = refresh(sources=["gmail", "canvas"], hours=24)
            success = [s for s, ok in results.items() if ok]
            failed  = [s for s, ok in results.items() if not ok]
            if success:
                st.success(f"Updated: {', '.join(success)}")
            if failed:
                st.warning(f"Failed: {', '.join(failed)}")

    # ── Feature cards ─────────────────────────────────────────────────────────
    st.markdown('<div class="section-label">What it knows</div>', unsafe_allow_html=True)

    st.markdown(f"""
    <div class="feat-grid">

      <div class="feat-card">
        <div class="feat-icon structured">📊</div>
        <div class="feat-title">Structured</div>
        <div class="feat-desc">Hard facts with timestamps. Deadlines, events, tasks.</div>
        <div class="feat-items">
          <div class="feat-item"><span class="feat-dot" style="background:#8bf0ba"></span>Calendar events & free blocks</div>
          <div class="feat-item"><span class="feat-dot" style="background:#8bf0ba"></span>Course deadlines & assignments</div>
          <div class="feat-item"><span class="feat-dot" style="background:#8bf0ba"></span>Upcoming conflicts</div>
        </div>
      </div>

      <div class="feat-card">
        <div class="feat-icon behavioral">🧠</div>
        <div class="feat-title">Behavioral</div>
        <div class="feat-desc">Inferred patterns from how you actually work. With confidence scores.</div>
        <div class="feat-items">
          <div class="feat-item"><span class="feat-dot" style="background:#8bf0ba"></span>Work style &amp; peak focus hours</div>
          <div class="feat-item"><span class="feat-dot" style="background:#8bf0ba"></span>Busiest days &amp; meeting patterns</div>
          <div class="feat-item"><span class="feat-dot" style="background:#8bf0ba"></span>Communication style</div>
        </div>
      </div>

      <div class="feat-card">
        <div class="feat-icon semantic">🔖</div>
        <div class="feat-title">Semantic</div>
        <div class="feat-desc">Long-term memory. Who you are, what you care about, relevant history.</div>
        <div class="feat-items">
          <div class="feat-item"><span class="feat-dot" style="background:#404060"></span>Relevant email &amp; calendar history</div>
          <div class="feat-item"><span class="feat-dot" style="background:#404060"></span>Identity tags &amp; active context</div>
          <div class="feat-item"><span class="feat-dot" style="background:#404060"></span>Semantic search over {layer["vectors"]:,} vectors</div>
        </div>
      </div>

    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── How it works ──────────────────────────────────────────────────────────
    st.markdown('<div class="section-label">How it works</div>', unsafe_allow_html=True)

    st.markdown("""
    <div class="steps">
      <div class="step">
        <div class="step-num">Step 01</div>
        <div class="step-title">Connect your sources</div>
        <div class="step-desc">Gmail, Google Calendar, Canvas, Notion, GitHub — any OAuth source. Configure once in <code>sources.json</code>.</div>
        <div class="step-code">python setup.py</div>
      </div>
      <div class="step">
        <div class="step-num">Step 02</div>
        <div class="step-title">Build once</div>
        <div class="step-desc">The layer ingests your data, embeds it into a vector database, and builds a behavioral profile. Initialized once, cached in memory.</div>
        <div class="step-code">30,247 vectors · ready</div>
      </div>
      <div class="step">
        <div class="step-num">Step 03</div>
        <div class="step-title">Any agent queries it</div>
        <div class="step-desc">LangChain, CrewAI, LlamaIndex, raw MCP — one call returns structured context for any task, in any framework.</div>
        <div class="step-code">context.get(task)</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── API surface ───────────────────────────────────────────────────────────
    st.markdown('<div class="section-label">API surface</div>', unsafe_allow_html=True)

    col_a, col_b = st.columns(2)
    with col_a:
        st.code("""# Platform API
from context_engine import context

ctx   = context.get("find study time")
sched = context.schedule()
prof  = context.energy_profile()
prefs = context.preferences("study")
dl    = context.deadlines()
mems  = context.memory("CS231N")""", language="python")

    with col_b:
        st.code("""# MCP — any framework
tools = await load_mcp_tools(session)

# LangChain
agent = create_react_agent(llm, tools)

# CrewAI
PersonalContextTool()

# LlamaIndex
FunctionTool.from_defaults(fn=context.get)""", language="python")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        '<div style="text-align:center;padding:20px 0">'
        '<span style="color:#7070a0;font-size:0.85rem">See it in action →</span>'
        '</div>',
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# DEMO
# ══════════════════════════════════════════════════════════════════════════════

with tab_demo:

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Controls ──────────────────────────────────────────────────────────────
    c1, c2 = st.columns([1, 3])
    with c1:
        platform = st.selectbox("Platform", list(PLATFORMS.keys()), label_visibility="visible")
    with c2:
        task_input = st.text_input(
            "Prompt",
            value=st.session_state.get("task", ""),
            placeholder="Ask anything — the context layer handles the rest",
        )
        if task_input:
            st.session_state["task"] = task_input

    st.markdown('<div class="section-label" style="margin-top:12px">Try these</div>',
                unsafe_allow_html=True)
    chip_cols = st.columns(3)
    for i, prompt in enumerate(EXAMPLE_PROMPTS):
        with chip_cols[i % 3]:
            short = prompt[:44] + "…" if len(prompt) > 44 else prompt
            if st.button(short, key=f"ex_{i}", use_container_width=True):
                st.session_state["task"] = prompt
                st.rerun()

    task = st.session_state.get("task", "")
    plat_icon = PLATFORMS[platform]

    st.markdown("")
    run = st.button("Run comparison", type="primary", disabled=not task)

    # ── Results ───────────────────────────────────────────────────────────────
    if run and task:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(
            f'<div style="font-size:0.78rem;color:#7070a0;margin-bottom:16px">'
            f'{plat_icon} &nbsp;·&nbsp; '
            f'<span style="color:#8bf0ba">{layer["vectors"]:,} vectors queried</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        col_naive, col_ctx, col_enhanced = st.columns(3)

        with col_naive:
            st.markdown(f'<div class="section-label">{plat_icon} — no context</div>',
                        unsafe_allow_html=True)
            st.caption("Stateless. No personal data.")
            naive_box = st.empty()
            naive_box.markdown('<div style="background:rgba(14,15,237,.08);border:1px solid #1a1a2e;border-radius:6px;padding:12px 16px;color:#7070a0;font-size:0.85rem">Running…</div>', unsafe_allow_html=True)

        with col_ctx:
            st.markdown('<div class="section-label">Context layer</div>',
                        unsafe_allow_html=True)
            st.caption("Querying your universal context layer.")
            ctx_box = st.empty()
            ctx_box.markdown('<div style="background:rgba(14,15,237,.08);border:1px solid #1a1a2e;border-radius:6px;padding:12px 16px;color:#7070a0;font-size:0.85rem">Querying layer…</div>', unsafe_allow_html=True)

        with col_enhanced:
            st.markdown(f'<div class="section-label">{plat_icon} + PersonalContext</div>',
                        unsafe_allow_html=True)
            st.caption("Same agent. Layer plugged in.")
            enhanced_box = st.empty()
            enhanced_box.markdown('<div style="background:rgba(14,15,237,.08);border:1px solid #1a1a2e;border-radius:6px;padding:12px 16px;color:#7070a0;font-size:0.85rem">Running…</div>', unsafe_allow_html=True)

        naive_fn, enhanced_fn = get_agents(platform)

        with ThreadPoolExecutor(max_workers=2) as pool:
            naive_f    = pool.submit(naive_fn, task)
            enhanced_f = pool.submit(enhanced_fn, task)
            naive_r             = naive_f.result()
            enhanced_r, context = enhanced_f.result()

        naive_box.markdown(naive_r)
        enhanced_box.markdown(enhanced_r)

        with col_ctx:
            ctx_box.empty()
            render_context_panel(context)

        st.markdown('<div class="section-label" style="margin-top:24px">Impact</div>',
                    unsafe_allow_html=True)
        render_diff_bar(naive_r, enhanced_r, context)

        st.markdown("<br>", unsafe_allow_html=True)
        exp1, exp2 = st.columns(2)
        with exp1:
            st.markdown(f'<div class="section-label">Without context</div>',
                        unsafe_allow_html=True)
            render_explain(task, naive_r, {}, "naive")
        with exp2:
            st.markdown(f'<div class="section-label">With PersonalContext</div>',
                        unsafe_allow_html=True)
            render_explain(task, enhanced_r, context, "enhanced")

        with st.expander("Raw PersonalContext object", expanded=False):
            st.json(context)

# ══════════════════════════════════════════════════════════════════════════════
# SETUP
# ══════════════════════════════════════════════════════════════════════════════

with tab_setup:
    st.markdown("<br>", unsafe_allow_html=True)

    def setup_step(n: int, title: str, description: str, code: str = None, note: str = None):
        """Render a single numbered setup step."""
        st.markdown(
            f'<div style="display:flex;gap:16px;margin-bottom:24px">'
            f'<div style="width:28px;height:28px;border-radius:50%;background:rgba(14,15,237,.2);'
            f'border:1px solid rgba(14,15,237,.4);display:flex;align-items:center;'
            f'justify-content:center;flex-shrink:0;font-size:0.75rem;font-weight:700;color:#6a6aff">'
            f'{n}</div>'
            f'<div style="flex:1">'
            f'<div style="font-size:0.95rem;font-weight:600;color:#94f0f1;margin-bottom:4px">{title}</div>'
            f'<div style="font-size:0.83rem;color:#7070b0;margin-bottom:{"10px" if code else "0"}">{description}</div>'
            f'</div></div>',
            unsafe_allow_html=True,
        )
        if code:
            st.code(code, language="bash")
        if note:
            st.markdown(
                f'<div style="background:rgba(139,240,186,.07);border:1px solid rgba(139,240,186,.2);'
                f'border-radius:6px;padding:8px 14px;font-size:0.78rem;color:#6ab88a;margin-bottom:16px">'
                f'💡 {note}</div>',
                unsafe_allow_html=True,
            )

    def prereq_badge(label: str, ok: bool):
        color = "#8bf0ba" if ok else "#f2b1d8"
        bg    = "rgba(139,240,186,.1)" if ok else "rgba(242,177,216,.1)"
        icon  = "✓" if ok else "✗"
        return (
            f'<div style="display:inline-flex;align-items:center;gap:6px;'
            f'background:{bg};border:1px solid {color}30;border-radius:6px;'
            f'padding:6px 12px;margin:4px;font-size:0.8rem;color:{color}">'
            f'<span>{icon}</span><span>{label}</span></div>'
        )

    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown(
        '<div style="margin-bottom:32px">'
        '<div style="font-size:1.5rem;font-weight:700;color:#94f0f1;margin-bottom:8px">'
        'Get started in 5 steps</div>'
        '<div style="color:#7070b0;font-size:0.9rem">'
        'From zero to a live context layer running against your own data.</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # ── System status ─────────────────────────────────────────────────────────
    st.markdown(
        '<div class="section-label">System status</div>',
        unsafe_allow_html=True,
    )

    import os
    from pathlib import Path as _P

    ROOT_PATH = _P(__file__).parent.parent
    checks = {
        "Python 3.11+":        sys.version_info >= (3, 11),
        "Agent venv":          (_P(__file__).parent.parent / "agent" / ".venv" / "Scripts" / "python.exe").exists(),
        "ANTHROPIC_API_KEY":   bool(os.environ.get("ANTHROPIC_API_KEY")),
        "Gmail OAuth":         (_P(__file__).parent.parent / "gmail-mcp" / "token.json").exists(),
        "Calendar OAuth":      (_P(__file__).parent.parent / "gcal-mcp"  / "token.json").exists(),
        "Canvas token":        bool(os.environ.get("CANVAS_TOKEN")),
        "Vector DB built":     (_P(__file__).parent.parent / "agent" / "db").exists(),
    }

    badges = "".join(prereq_badge(k, v) for k, v in checks.items())
    all_ok = all(checks.values())
    st.markdown(
        f'<div style="margin-bottom:24px">{badges}</div>'
        f'<div style="font-size:0.8rem;color:{"#8bf0ba" if all_ok else "#f2b1d8"};margin-bottom:32px">'
        f'{"✓ Everything is ready. Run the demo." if all_ok else "Some prerequisites are missing — follow the steps below."}'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Steps ─────────────────────────────────────────────────────────────────
    st.markdown('<div class="section-label">Setup steps</div>', unsafe_allow_html=True)

    setup_step(
        1, "Clone the repo & install dependencies",
        "Requires Python 3.11+ and uv. The agent venv installs all packages "
        "including ChromaDB, sentence-transformers, and Google API libraries.",
        code=(
            "git clone https://github.com/your-username/PersonalAgent\n"
            "cd PersonalAgent/agent\n"
            "uv sync          # creates .venv and installs everything"
        ),
        note="First run downloads the all-MiniLM-L6-v2 embedding model (~90 MB). Takes 2–3 min.",
    )

    setup_step(
        2, "Add your API keys",
        "Create agent/.env with your Anthropic API key and Canvas token. "
        "Or run the guided setup wizard which prompts for each key.",
        code=(
            "# Option A — guided wizard (recommended)\n"
            "python setup.py\n\n"
            "# Option B — create .env manually\n"
            "# agent/.env\n"
            "ANTHROPIC_API_KEY=sk-ant-...\n"
            "CANVAS_TOKEN=your_canvas_token_here\n"
            "PYTHONIOENCODING=utf-8"
        ),
        note="Get your Anthropic key at console.anthropic.com. Canvas token: Account → Settings → New Access Token.",
    )

    setup_step(
        3, "Connect Google OAuth (Gmail + Calendar)",
        "Download OAuth credentials from Google Cloud Console, then run the auth script "
        "for each service. A browser window opens once — approve access and the token is saved.",
        code=(
            "# 1. Go to console.cloud.google.com\n"
            "# 2. Enable Gmail API + Calendar API\n"
            "# 3. Create OAuth 2.0 credentials (Desktop app)\n"
            "# 4. Save as credentials.json in both gmail-mcp/ and gcal-mcp/\n\n"
            "cd gmail-mcp  && python auth.py\n"
            "cd ../gcal-mcp && python auth.py"
        ),
        note="Only needed once. Tokens auto-refresh. Same Google Cloud project works for both.",
    )

    setup_step(
        4, "Build your context layer",
        "Ingests your data from all connected sources, embeds it into a vector database, "
        "and generates a behavioral profile. Run from the agent/ directory.",
        code=(
            "cd agent\n\n"
            "python ingest.py          # pulls Gmail, Calendar, Canvas, course sites\n"
            "python embed.py           # builds ChromaDB vector database\n"
            "python behavioral_profile.py   # generates data/profile.json"
        ),
        note="Ingest takes ~2 min for Gmail (2,000 emails). Embed takes ~3 min for 30k vectors.",
    )

    setup_step(
        5, "Run the demo",
        "Activate the agent venv and launch any of the three demo apps.",
        code=(
            "# Activate the venv first\n"
            "agent\\.venv\\Scripts\\Activate.ps1    # Windows\n"
            "source agent/.venv/bin/activate      # macOS / Linux\n\n"
            "# Main product demo (Home + Demo tabs)\n"
            "streamlit run demo/app.py\n\n"
            "# Universal 3-step wizard (configure → build → test)\n"
            "streamlit run demo/universal_app.py\n\n"
            "# Agent builder (configure, test live, export code)\n"
            "streamlit run demo/builder_app.py"
        ),
    )

    # ── Check status / run pipeline button ───────────────────────────────────
    st.markdown('<div class="section-label" style="margin-top:16px">Quick commands</div>',
                unsafe_allow_html=True)

    qc1, qc2 = st.columns(2)
    with qc1:
        st.markdown("**Check setup status**")
        st.code("python setup.py --check", language="bash")
        st.markdown("**Re-run setup wizard**")
        st.code("python setup.py", language="bash")
    with qc2:
        st.markdown("**Re-ingest a single source**")
        st.code("python agent/ingest.py --source gmail", language="bash")
        st.markdown("**Run the eval suite**")
        st.code("python eval/eval_suite.py --cases scheduling email", language="bash")

    st.divider()

    # ── Data sources reference ────────────────────────────────────────────────
    st.markdown('<div class="section-label">Data sources reference</div>',
                unsafe_allow_html=True)

    sources_data = [
        ("Gmail",           "gmail-mcp/token.json",    "OAuth",  "inbox, sent, receipts"),
        ("Google Calendar", "gcal-mcp/token.json",     "OAuth",  "events, free blocks"),
        ("Canvas LMS",      "CANVAS_TOKEN in .env",    "Token",  "courses, assignments, deadlines"),
        ("Course websites", "none required",           "Public", "scraped schedules"),
        ("Notion",          "NOTION_TOKEN in .env",    "Token",  "notes, documents"),
        ("GitHub",          "GITHUB_TOKEN in .env",    "Token",  "commits, PRs, issues"),
    ]

    header = (
        '<div style="display:grid;grid-template-columns:1.2fr 1.8fr 0.8fr 2fr;'
        'gap:12px;padding:8px 12px;font-size:0.65rem;color:#303050;'
        'text-transform:uppercase;letter-spacing:0.1em;border-bottom:1px solid #1a1a2e">'
        '<div>Source</div><div>Credentials</div><div>Type</div><div>Provides</div></div>'
    )
    rows = ""
    for name, creds, ctype, provides in sources_data:
        connected = checks.get(name.split()[0] + " OAuth", checks.get(name.split()[0], False))
        dot_color = "#8bf0ba" if connected else "#1a1a2e"
        rows += (
            f'<div style="display:grid;grid-template-columns:1.2fr 1.8fr 0.8fr 2fr;'
            f'gap:12px;padding:10px 12px;font-size:0.8rem;border-bottom:1px solid #141420;'
            f'align-items:center">'
            f'<div style="display:flex;align-items:center;gap:6px">'
            f'<span style="width:6px;height:6px;border-radius:50%;background:{dot_color};flex-shrink:0"></span>'
            f'<span style="color:#c8d8ff">{name}</span></div>'
            f'<div style="font-family:monospace;font-size:0.72rem;color:#6060a0">{creds}</div>'
            f'<div style="color:#7070b0">{ctype}</div>'
            f'<div style="color:#7070b0">{provides}</div>'
            f'</div>'
        )
    st.markdown(
        f'<div style="background:#0e0e18;border:1px solid #1a1a2e;border-radius:8px;overflow:hidden">'
        f'{header}{rows}</div>',
        unsafe_allow_html=True,
    )
