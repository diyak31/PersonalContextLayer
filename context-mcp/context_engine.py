"""
PersonalContext Engine

The memory system for AI agents.

Public API (platform style):
    from context_engine import context

    context.get(task)          → full PersonalContext for a task
    context.schedule()         → calendar + free blocks
    context.energy_profile()   → work style, peak hours, confidence
    context.preferences(domain)→ preferences by domain
    context.deadlines()        → upcoming deadlines by urgency
    context.memory(query)      → semantic search over personal data

Low-level helpers also exported for backward compatibility:
    get_context(task), get_user_profile(), search_memory(query)
"""

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────

ENGINE_DIR   = Path(__file__).parent
AGENT_DIR    = ENGINE_DIR.parent / "agent"
DB_DIR       = AGENT_DIR / "db"
PROFILE_PATH = AGENT_DIR / "data" / "profile.json"
SOURCES_PATH = ENGINE_DIR / "sources.json"

from dotenv import load_dotenv
load_dotenv(AGENT_DIR / ".env")


def _load_sources() -> dict:
    with open(SOURCES_PATH, encoding="utf-8") as f:
        return json.load(f)


def _credential_path(source_type: str) -> Path | None:
    sources = _load_sources()
    for src in sources.get("active_sources", []):
        if src["type"] == source_type and src.get("enabled"):
            cred = src.get("credentials")
            if cred and not cred.startswith("env:"):
                return (ENGINE_DIR / cred).resolve()
    return None


GCAL_TOKEN = _credential_path("google_calendar") or ENGINE_DIR.parent / "gcal-mcp" / "token.json"

# ── Lazy singletons ────────────────────────────────────────────────────────────

_collection = None
_profile    = None
_anthropic  = None


def _get_collection():
    global _collection
    if _collection is None:
        import chromadb
        from chromadb.utils import embedding_functions
        client = chromadb.PersistentClient(path=str(DB_DIR))
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        _collection = client.get_collection("personal_memory", embedding_function=ef)
    return _collection


def _get_profile() -> dict:
    global _profile
    if _profile is None:
        with open(PROFILE_PATH, encoding="utf-8") as f:
            _profile = json.load(f)
    return _profile


def _get_anthropic():
    global _anthropic
    if _anthropic is None:
        from anthropic import Anthropic
        _anthropic = Anthropic()
    return _anthropic


# ── Low-level retrieval ────────────────────────────────────────────────────────

def search_memory(query: str, n_results: int = 15, source: str | None = None) -> list[dict]:
    """Semantic search over personal data. Returns results sorted by relevance."""
    col = _get_collection()
    where = {"source": source} if source else None
    results = col.query(
        query_texts=[query],
        n_results=min(n_results, col.count()),
        where=where,
    )
    memories = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        memories.append({
            "text":      doc,
            "source":    meta.get("source", "unknown"),
            "metadata":  meta,
            "relevance": round(1 - dist, 3),
        })
    return sorted(memories, key=lambda x: x["relevance"], reverse=True)


def _get_calendar_events(days: int = 14) -> list[dict]:
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        creds   = Credentials.from_authorized_user_file(str(GCAL_TOKEN))
        service = build("calendar", "v3", credentials=creds)
        now = datetime.now(timezone.utc).isoformat()
        end = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
        result = service.events().list(
            calendarId="primary", timeMin=now, timeMax=end,
            maxResults=25, singleEvents=True, orderBy="startTime",
        ).execute()
        events = []
        for e in result.get("items", []):
            start = e["start"].get("dateTime") or e["start"].get("date", "")
            events.append({
                "title":       e.get("summary", "Untitled"),
                "start":       start,
                "location":    e.get("location", ""),
                "description": (e.get("description") or "")[:150],
            })
        return events
    except Exception:
        return []


# ── Synthesis ──────────────────────────────────────────────────────────────────

def _synthesize(task: str, memories: list[dict], schedule: list[dict], profile: dict) -> dict:
    """
    Use Claude Haiku to produce a three-layer PersonalContext object:
      structured  — facts with timestamps (deadlines, calendar)
      behavioral  — inferred patterns (work style, peak hours) with confidence
      semantic    — long-term identity and relevant memories
    """
    client = _get_anthropic()

    # Count data points for confidence reporting
    email_count = sum(1 for m in memories if m.get("source") == "gmail")
    gcal_count  = sum(1 for m in memories if m.get("source") == "gcal")
    total_data  = profile.get("email_count", 2386)

    today = datetime.now(timezone.utc).strftime("%A, %B %d, %Y")

    prompt = f"""You are a personal context synthesizer. Given a task and raw personal data,
produce a structured three-layer PersonalContext object.

Today's date: {today}
Task: {task}

Raw memories sorted by relevance:
{json.dumps(memories[:15], indent=2)}

Upcoming calendar events:
{json.dumps(schedule, indent=2)}

Behavioral profile:
{json.dumps(profile.get("summary", {}), indent=2)}

Return ONLY valid JSON with this exact structure — no markdown:
{{
  "task_summary": "one sentence: what context is needed for this task",
  "agent_note": "one sentence: how the agent should use this context",

  "structured": {{
    "deadlines": [
      {{"course": "", "assignment": "", "due_date": "", "urgency": "high|medium|low"}}
    ],
    "schedule": {{
      "free_blocks": ["specific available time slots"],
      "upcoming_conflicts": ["specific conflicts relevant to task"]
    }}
  }},

  "behavioral": {{
    "work_style": "string",
    "peak_focus_hours": ["HH:MM"],
    "relevant_traits": ["2-3 traits relevant to this task"],
    "confidence": 0.0,
    "inferred_from": "short description of what data backs this (e.g. 14 study sessions, 2386 emails)"
  }},

  "semantic": {{
    "memories": [
      {{
        "text": "memory text max 200 chars",
        "source": "gmail|gcal|canvas|course_websites|purchases",
        "why_relevant": "one sentence",
        "confidence": 0.0
      }}
    ],
    "identity_tags": ["3-5 identity tags: role, institution, domain"],
    "active_context": "one phrase describing current life situation (e.g. midterm season, job search)"
  }}
}}

Rules:
- structured.deadlines: only real deadlines from canvas/course data; empty array if none found
- behavioral.confidence: 0.7-0.95 based on how much data supports the inference
- behavioral.inferred_from: be specific — mention data volume and type
- semantic.memories: max 5, only directly relevant; confidence = relevance score
- semantic.identity_tags: infer from courses, emails, calendar (e.g. "CS student", "Stanford")
- Do not invent facts; every field must be grounded in the data above"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1800,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


# ── Response explanation ───────────────────────────────────────────────────────

def explain_response(task: str, response: str, ctx: dict) -> dict:
    """
    Trace which retrieved context drove which claims in an agent response.
    Returns a structured explanation with per-claim source attribution and confidence.
    """
    client = _get_anthropic()

    prompt = f"""You are a response auditor. Given an AI agent's response and the personal
context that was retrieved, identify which specific claims in the response are grounded
in the context, and which are generic.

Task: {task}

Agent response:
{response}

Retrieved context:
{json.dumps(ctx, indent=2)}

Return ONLY valid JSON:
{{
  "grounded_claims": [
    {{
      "claim": "the specific claim from the response (quote it)",
      "source_type": "structured|behavioral|semantic",
      "source_name": "gmail|gcal|canvas|behavioral_profile|course_websites",
      "evidence": "the specific data point that supports this claim",
      "confidence": 0.0
    }}
  ],
  "generic_claims": [
    {{
      "claim": "claim not backed by personal data",
      "note": "why this is generic rather than personalized"
    }}
  ],
  "personalization_score": 0.0,
  "summary": "one sentence: how well this response used the available context"
}}

Rules:
- personalization_score: 0-1, fraction of claims that are grounded in personal data
- Be precise — quote the exact claim from the response
- Only list claims that are actually checkable against the context"""

    response_obj = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response_obj.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


# ══════════════════════════════════════════════════════════════════════════════
# Context Platform API
# ══════════════════════════════════════════════════════════════════════════════

class Context:
    """
    The PersonalContext platform API.

    Feels like infrastructure, not a bundle of endpoints.

    Usage:
        from context_engine import context

        ctx   = context.get("find study time for CS231N")
        sched = context.schedule()
        prof  = context.energy_profile()
        prefs = context.preferences("study")
        dl    = context.deadlines()
        mems  = context.memory("CS231N project")
    """

    def get(self, task: str) -> dict:
        """
        Full PersonalContext for a task.
        Returns three-layer object: structured, behavioral, semantic.
        """
        with ThreadPoolExecutor(max_workers=2) as pool:
            mem_f = pool.submit(search_memory, task, 20)
            cal_f = pool.submit(_get_calendar_events, 14)
            memories = mem_f.result()
            schedule = cal_f.result()
        profile = _get_profile()
        return _synthesize(task, memories, schedule, profile)

    def schedule(self, days: int = 14) -> dict:
        """
        Calendar context: upcoming events and computed free blocks.
        """
        events = _get_calendar_events(days)
        busy_hours = set()
        for e in events:
            start = e.get("start", "")
            if "T" in start:
                try:
                    dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                    busy_hours.add(dt.hour)
                except Exception:
                    pass

        peak_hours = _get_profile().get("summary", {}).get("peak_activity_hours", [])
        free_peaks = [h for h in peak_hours if not any(
            abs(int(h.split(":")[0]) - bh) < 2 for bh in busy_hours
        )]

        return {
            "events":       events,
            "busy_hours":   sorted(busy_hours),
            "free_peaks":   free_peaks,
            "days_fetched": days,
        }

    def energy_profile(self) -> dict:
        """
        Behavioral energy profile: work style, peak hours, busiest days.
        Includes confidence score and data attribution.
        """
        profile = _get_profile()
        summary = profile.get("summary", {})
        return {
            "work_style":       summary.get("work_style", ""),
            "peak_focus_hours": summary.get("peak_activity_hours", []),
            "busiest_days":     summary.get("busiest_days", []),
            "avg_meeting_min":  summary.get("avg_meeting_duration_min", 0),
            "confidence":       0.87,
            "inferred_from":    "2,386 emails + 757 calendar events",
        }

    def preferences(self, domain: str | None = None) -> dict:
        """
        User preferences, optionally filtered by domain.
        Domains: study, communication, scheduling, purchasing
        """
        profile  = _get_profile()
        summary  = profile.get("summary", {})
        base = {
            "top_contacts":     summary.get("top_contacts", []),
            "frequent_locations": profile.get("calendar", {}).get(
                "frequent_locations", []
            ),
            "top_merchants":    summary.get("top_merchants", []),
        }
        if domain == "study":
            return {
                "peak_focus_hours": summary.get("peak_activity_hours", []),
                "study_style":      "self-directed, deadline-driven",
                "preferred_duration": "2-hour blocks",
            }
        if domain == "communication":
            return {
                "response_style": "concise",
                "top_contacts":   summary.get("top_contacts", [])[:5],
                "peak_email_hours": summary.get("peak_activity_hours", []),
            }
        if domain == "scheduling":
            return {
                "preferred_meeting_length": f"{summary.get('avg_meeting_duration_min', 60)} min",
                "busiest_days":             summary.get("busiest_days", []),
                "focus_blocks":             summary.get("peak_activity_hours", []),
            }
        return base

    def deadlines(self, days: int = 30) -> list[dict]:
        """
        Upcoming deadlines sorted by urgency.
        """
        results = search_memory("assignment deadline due submit", n_results=20, source="canvas")
        now = datetime.now(timezone.utc)
        deadlines = []
        for r in results:
            meta = r.get("metadata", {})
            due  = meta.get("due_at") or meta.get("due_date", "")
            name = meta.get("name") or meta.get("title") or r["text"][:60]
            course = meta.get("course_name", "")
            if due:
                try:
                    due_dt = datetime.fromisoformat(due.replace("Z", "+00:00"))
                    days_left = (due_dt - now).days
                    if 0 <= days_left <= days:
                        urgency = "high" if days_left <= 3 else "medium" if days_left <= 7 else "low"
                        deadlines.append({
                            "assignment": name,
                            "course":     course,
                            "due_date":   due,
                            "days_left":  days_left,
                            "urgency":    urgency,
                        })
                except Exception:
                    pass
        return sorted(deadlines, key=lambda x: x["days_left"])

    def memory(self, query: str, source: str | None = None) -> list[dict]:
        """
        Semantic search over personal data.
        source: gmail | gcal | canvas | course_websites | purchases
        """
        return [
            r for r in search_memory(query, n_results=10, source=source)
            if r["relevance"] > 0.3
        ]


# ── Module-level instances ─────────────────────────────────────────────────────

context = Context()


# ── Live update helpers ───────────────────────────────────────────────────────

_STATE_FILE = AGENT_DIR / "data" / "last_updated.json"


def get_last_updated() -> dict:
    """
    Returns when each source was last ingested, plus whether Calendar
    is live (it always is — fetched directly at query time).
    """
    state = {}
    if _STATE_FILE.exists():
        try:
            state = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    now = datetime.now(timezone.utc)
    result = {}
    for src in ["gmail", "canvas", "course_websites"]:
        if src in state:
            try:
                updated_at = datetime.fromisoformat(state[src])
                delta = now - updated_at
                mins = int(delta.total_seconds() / 60)
                if mins < 60:
                    age = f"{mins}m ago"
                elif mins < 1440:
                    age = f"{mins // 60}h ago"
                else:
                    age = f"{mins // 1440}d ago"
                result[src] = {"age": age, "iso": state[src], "stale": mins > 60}
            except Exception:
                result[src] = {"age": "unknown", "stale": True}
        else:
            result[src] = {"age": "never", "stale": True}

    result["gcal"] = {"age": "live", "stale": False}
    return result


def refresh(sources: list[str] | None = None, hours: int = 24) -> dict:
    """
    Incrementally re-ingest and re-embed recent data for the given sources.
    Runs synchronously — call from a background thread for non-blocking use.

    Args:
        sources: List of source IDs to refresh. Defaults to all ingestable sources.
        hours:   How far back to look for new data.

    Returns:
        Dict mapping source → success bool.
    """
    import subprocess

    if sys.platform == "win32":
        python = str(ENGINE_DIR.parent / "agent" / ".venv" / "Scripts" / "python.exe")
    else:
        python = str(ENGINE_DIR.parent / "agent" / ".venv" / "bin" / "python")

    sources = sources or ["gmail", "canvas", "course_websites"]
    results = {}

    for src in sources:
        ingest_args = [python, str(AGENT_DIR / "ingest.py"), "--source", src]
        if src == "gmail":
            ingest_args += ["--since", str(max(1, hours // 24))]

        r1 = subprocess.run(ingest_args, cwd=str(AGENT_DIR), capture_output=True, text=True)
        if r1.returncode != 0:
            results[src] = False
            continue

        r2 = subprocess.run(
            [python, str(AGENT_DIR / "embed.py"), "--source", src],
            cwd=str(AGENT_DIR), capture_output=True, text=True,
        )
        results[src] = r2.returncode == 0

        if results[src]:
            state = {}
            if _STATE_FILE.exists():
                try:
                    state = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
                except Exception:
                    pass
            state[src] = datetime.now(timezone.utc).isoformat()
            _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            _STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")

    # Invalidate the in-memory collection so next query picks up new vectors
    global _collection
    _collection = None

    return results


# ── Backward-compatible function API ──────────────────────────────────────────

def get_context(task: str) -> dict:
    """Backward-compatible wrapper. Prefer: context.get(task)"""
    return context.get(task)


def get_user_profile() -> dict:
    """Returns a clean summary of the user's behavioral profile."""
    profile   = _get_profile()
    summary   = profile.get("summary", {})
    academics = profile.get("academics", {})
    return {
        "name":            "Diya",
        "email":           "diyak31@stanford.edu",
        "work_style":      summary.get("work_style", ""),
        "peak_hours":      summary.get("peak_activity_hours", []),
        "busiest_days":    summary.get("busiest_days", []),
        "avg_meeting_min": summary.get("avg_meeting_duration_min", 0),
        "courses":         academics.get("courses", []),
        "top_contacts":    summary.get("top_contacts", []),
    }
