# PersonalContext

**The memory system for AI agents.**

One call. Any agent framework. Full personal context — structured, behavioral, and semantic.

---

## What this is

Every AI agent has the same problem: the moment you ask it something personal, it says that it doesn't have access to your personal data and is essentially useless. Every time. No matter how capable the model.

PersonalContext is a universal context layer that solves this. It ingests your personal data (Gmail, Google Calendar, Canvas, course websites), embeds it into a vector database, and exposes it through a standard MCP interface that any agent framework can call. Agents built on top of it answer specifically and directly — without being told anything about you first.

> **"What Firebase is to data, PersonalContext is to context."**

This project was built for CS 153: Frontier Systems, under the prompt *"One person with the right AI tools can now produce what once required an organization."*

---

## Demo

```bash
# Install dependencies
cd agent && uv sync

# Run guided setup (API keys + OAuth + pipeline)
python setup.py

# Launch the demo
streamlit run demo/app.py
```

The demo has three tabs: **Home** (product overview), **Demo** (live before/after comparison across agent frameworks), and **Setup** (step-by-step instructions with live status checks).

To keep the context layer fresh while the demo runs, start the live updater in a second terminal:

```bash
python context-mcp/live_updater.py        # auto-refreshes on a schedule
python context-mcp/live_updater.py --once # run once and exit
```

---

## Architecture

```
Personal data sources
  Gmail · Google Calendar · Canvas · Course websites
        │
        ▼
  agent/ingest.py          ← pulls raw data to JSONL
  agent/embed.py           ← chunks + embeds into ChromaDB (~30k vectors)
  agent/behavioral_profile.py  ← infers patterns from raw data
        │
        ▼
  context-mcp/context_engine.py   ← core synthesis engine
        │
        ├── context.get(task)          → full PersonalContext
        ├── context.schedule()         → calendar + free blocks  [always live]
        ├── context.energy_profile()   → work style, peak hours, confidence
        ├── context.preferences(domain)→ preferences by domain
        ├── context.deadlines()        → upcoming deadlines
        ├── context.memory(query)      → semantic search
        ├── get_last_updated()         → data freshness per source
        └── refresh(sources, hours)    → incremental re-ingest + re-embed
        │
  context-mcp/live_updater.py  ← background auto-refresh process
        │                          Gmail every 30 min · Canvas every 60 min
        │                          Course sites every 6 hours · Calendar always live
        ▼
  context-mcp/server.py    ← FastMCP server (MCP protocol)
        │
  Any agent framework
  LangChain · CrewAI · LlamaIndex · Raw MCP · Custom
```

### Three memory layers

| Layer | What it contains | Example |
|---|---|---|
| **Structured** | Hard facts with timestamps | CS231N deadline in 8 days, free block Thursday 6pm |
| **Behavioral** | Inferred patterns + confidence score | Evening person, peak focus 18:00 (87% confidence, from 2,386 emails) |
| **Semantic** | Long-term memories + identity | Relevant email threads, identity tags, active context |

---

## Evaluation

Ran a formal eval suite across 5 test cases (scheduling, email drafting, week planning, contact recall, spending) using an LLM-as-judge scorer:

| Metric | Without context | With PersonalContext |
|---|---|---|
| Response quality (1–10) | 3.4 | 5.6 |
| Specificity (named entities) | 5 | 26 |
| Asked for clarification | 5/5 tasks | 2/5 tasks |

The scheduling scenario is the strongest case: +6 quality points, +15 specific entities, clarification eliminated.

Run it yourself:
```bash
python eval/eval_suite.py
python eval/eval_suite.py --cases scheduling email   # fastest
```

---

## Project structure

```
PersonalAgent/
├── agent/                    # data pipeline + orchestrator
│   ├── ingest.py             # pulls data from all sources
│   ├── embed.py              # chunks + stores in ChromaDB
│   ├── behavioral_profile.py # builds JSON behavioral profile
│   ├── query.py              # semantic search interface
│   └── orchestrator.py       # original Claude-powered agent
│
├── context-mcp/              # the context layer
│   ├── context_engine.py     # core logic + Context class + explain_response() + refresh()
│   ├── server.py             # FastMCP server
│   ├── live_updater.py       # background auto-refresh process (schedule-based)
│   └── sources.json          # pluggable data source config
│
├── demo/                     # Streamlit demo apps
│   ├── app.py                # main product demo (Home + Demo + Setup tabs)
│   ├── universal_app.py      # 3-step wizard (configure → build → test)
│   ├── builder_app.py        # agent builder with code generation + deployment
│   ├── platforms_app.py      # platform integrations reference
│   └── agents.py             # naive + enhanced agent implementations
│
├── eval/
│   └── eval_suite.py         # LLM-as-judge evaluation across 5 test cases
│
├── gmail-mcp/                # Gmail MCP server
├── gcal-mcp/                 # Google Calendar MCP server
├── canvas-mcp/               # Canvas LMS MCP server
├── course-websites-mcp/      # Course website scraper MCP server
├── gradescope-mcp/           # Gradescope MCP server
└── setup.py                  # guided setup wizard
```

---

## Setup

### Prerequisites
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- Anthropic API key ([console.anthropic.com](https://console.anthropic.com))
- Google Cloud project with Gmail + Calendar APIs enabled

### Step 1 — Install
```bash
git clone https://github.com/your-username/PersonalAgent
cd PersonalAgent/agent
uv sync
```

### Step 2 — Configure
```bash
# Guided wizard (recommended) — handles API keys + OAuth + pipeline
python setup.py

# Or check current status
python setup.py --check
```

### Step 3 — Build context layer
```bash
cd agent
python ingest.py              # ~2 min for Gmail
python embed.py               # ~3 min for 30k vectors
python behavioral_profile.py
```

### Step 4 — Run
```bash
agent\.venv\Scripts\Activate.ps1     # Windows
source agent/.venv/bin/activate      # macOS/Linux

# Terminal 1 — demo UI
streamlit run demo/app.py

# Terminal 2 (optional) — keep context layer fresh automatically
python context-mcp/live_updater.py
```

### Keeping data fresh

The context layer updates in two ways:

| Source | Method | Frequency |
|---|---|---|
| Google Calendar | Direct API call at query time | **Always live** |
| Gmail | Incremental ingest (last 24h of emails) | Every 30 min |
| Canvas | Full re-pull (small dataset) | Every 60 min |
| Course websites | Full re-scrape | Every 6 hours |

The live updater runs as a separate process. You can also trigger a manual refresh from the **Refresh now** button in the demo UI, or from the command line:

```bash
python context-mcp/live_updater.py --once              # refresh all sources once
python context-mcp/live_updater.py --source gmail      # refresh one source
python context-mcp/live_updater.py --source gmail --hours 2  # last 2 hours only
```

Data freshness per source is shown in the demo UI header and tracked in `agent/data/last_updated.json`.

### Data sources
| Source | Auth | Provides |
|---|---|---|
| Gmail | OAuth (`gmail-mcp/auth.py`) | Email history, sent messages, receipts |
| Google Calendar | OAuth (`gcal-mcp/auth.py`) | Events, free blocks |
| Canvas LMS | Token (`CANVAS_TOKEN` in `.env`) | Courses, assignments, deadlines |
| Course websites | None (public scrape) | Schedules, deadlines |
| Notion | Token (`NOTION_TOKEN` in `.env`) | Notes, documents |
| GitHub | Token (`GITHUB_TOKEN` in `.env`) | Commits, PRs |

---

## Limitations

- **Single-user only**: credentials and profile are hardwired to one user. Multi-user support would require a config-per-user pattern and hosted OAuth. This will be implemented in the future. 
- **Data freshness**: Google Calendar is always live. Gmail and Canvas are refreshed incrementally by `live_updater.py` (every 30–60 min). True real-time streaming (push webhooks) is not yet implemented, but will be in the future. 
- **Synthesis latency**: `get_context(task)` calls Claude Haiku internally (~1–2s). ChromaDB search and Calendar fetch run in parallel to minimize this.
- **Sparse data edge cases**: for queries like "who do I email most," the context layer falls back to plain Claude when retrieval confidence is low.
- **eval/eval_suite.py uses LLM-as-judge**: scores are directionally correct but not ground truth. A hand-labeled dataset would be more rigorous.

---

## AI Usage Disclosure

This project was built in collaboration with **Claude Code** (Anthropic), used as the primary development assistant throughout. Here is an honest account of where and how AI tools were used:

### Ideation and direction
All major product decisions — the framing as a "universal context layer," the three-layer memory architecture (Structured/Behavioral/Semantic), the MCP interface choice, the demo structure, and the pivot away from earlier directions — were made through iterative conversation with Claude Code. I directed the vision; Claude helped evaluate tradeoffs and narrow scope.

### Code implementation
Essentially all code in this repository was written by Claude Code based on specifications and direction from me. This includes:
- `context_engine.py` — the core synthesis engine, Context class, `explain_response()`, `get_last_updated()`, and `refresh()`
- `live_updater.py` — background auto-refresh process with incremental ingest scheduling
- `server.py` — the FastMCP server and tool definitions
- All Streamlit demo apps (`app.py`, `universal_app.py`, `builder_app.py`, `platforms_app.py`)
- `eval/eval_suite.py` — evaluation framework and LLM-as-judge scoring
- `setup.py` — the guided setup wizard
- All CSS styling and UI design

The MCP servers (`gmail-mcp/`, `gcal-mcp/`, `canvas-mcp/`, `course-websites-mcp/`, `gradescope-mcp/`) were scaffolded using Claude code.

### What I contributed
- Defining and repeatedly refining the product direction through ~50+ conversation turns
- Running and interpreting all evaluations, identifying what was and wasn't working
- Making all taste/judgment calls on UI design, color palette, and demo narrative
- Debugging integration issues (venv, auth flows, Windows encoding)
- Deciding what to cut, what to keep, and what to build next

### Tools used
| Tool | Usage |
|---|---|
| Claude Code (claude-sonnet-4-6) | Primary coding assistant — all implementation |
| Claude API (claude-haiku-4-5) | Runtime: context synthesis + response explanation |
| Claude API (claude-sonnet-4-6) | Runtime: agent responses in demo |


---

## Acknowledgments

- [FastMCP](https://github.com/jlowin/fastmcp) — MCP server framework
- [ChromaDB](https://www.trychroma.com/) — vector database
- [sentence-transformers](https://www.sbert.net/) — `all-MiniLM-L6-v2` embedding model
- [Streamlit](https://streamlit.io/) — demo UI framework
- [Anthropic](https://www.anthropic.com/) — Claude API
- CS 153: Frontier Systems (Stanford, Spring 2026) — course project prompt

---

*Built for CS 153: Frontier Systems, Stanford University, Spring 2026.*
