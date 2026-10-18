"""
agent.py — OrgMind's brain
==========================
This file is the "thinking" part of our project.

A CHILD'S PICTURE OF WHAT HAPPENS
---------------------------------
1. You ask a question in words (English).
2. Gemini (the AI) reads the question.
3. Gemini is NOT allowed to guess about the company.
   It must pick a TOOL, like "look up who uses PostgreSQL".
4. The tool runs a Cypher question on FalkorDB (our mind-map database).
5. FalkorDB returns real connections (Alice → AuthService → PostgreSQL).
6. Gemini writes a human answer from THOSE facts.
7. We save the question + answer in the graph, so next time it remembers.

That is why the graph does REAL work. If we unplug FalkorDB, OrgMind
cannot look up the company. Gemini alone does not know Alice or AuthService.
"""
import re
import time
from google.api_core.exceptions import ResourceExhausted, NotFound
import os
from datetime import datetime

from dotenv import load_dotenv
import google.generativeai as genai

from db import get_connection

load_dotenv()

# Tell the Gemini library our secret key (from .env)
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Try a few model names. Google renames them sometimes; first one that
# works on your key will be used.
MODEL_CANDIDATES = [
    "gemini-3.5-flash-lite",   # 15/min, 500/day  (first choice)
    "gemini-3.1-flash-lite",   # 15/min, 500/day  (second choice)
    "gemini-2.5-flash-lite",   # 10/min, 20/day   (backup)
    "gemini-3.8-flash",        # 5/min, 20/day    (emergency)
    "gemini-2.5-flash",        # 5/min, 20/day    (emergency)
]

def _run_cypher(cypher, params=None):
    """
    Send a Cypher question to FalkorDB and get rows back.

    Cypher is the language of the graph, like English for people.
    Example: MATCH (p:Person) RETURN p.name
    means "find every Person bubble and tell me its name".
    """
    graph = get_connection()
    result = graph.query(cypher, params or {})
    rows = result.result_set or []
    # Turn [[ "Alice", "Backend" ]] into readable lines
    lines = []
    for row in rows:
        lines.append(" | ".join(str(item) for item in row))
    return "\n".join(lines) if lines else "(no matching rows in the graph)"


# ---------------------------------------------------------------------------
# TOOLS — each one is a specific question we can ask the mind-map
# ---------------------------------------------------------------------------

def who_works_on_project(project_name: str) -> str:
    """People linked to a project with WORKS_ON."""
    return _run_cypher(
        """
        MATCH (p:Person)-[:WORKS_ON]->(proj:Project)
        WHERE toLower(proj.name) CONTAINS toLower($name)
        RETURN p.name AS person, p.role AS role, p.team AS team, proj.name AS project
        """,
        {"name": project_name},
    )


def who_knows_system(system_name: str) -> str:
    """
    MULTI-HOP (Track 1): Person → project → system.

    We do not store "Alice knows PostgreSQL" as a flat fact.
    We FOLLOW the lines: Alice WORKS_ON AuthService, AuthService USES PostgreSQL.
    """
    return _run_cypher(
        """
        MATCH (p:Person)-[:WORKS_ON]->(proj:Project)-[:USES]->(s:System)
        WHERE toLower(s.name) CONTAINS toLower($name)
        RETURN p.name AS person, p.role AS role,
               proj.name AS project, s.name AS system
        """,
        {"name": system_name},
    )


def impact_if_system_down(system_name: str) -> str:
    """If this system breaks, which projects and people are on the path?"""
    return _run_cypher(
        """
        MATCH (p:Person)-[:WORKS_ON]->(proj:Project)-[:USES]->(s:System)
        WHERE toLower(s.name) CONTAINS toLower($name)
        RETURN s.name AS system, proj.name AS project,
               proj.status AS status, p.name AS person, p.role AS role
        """,
        {"name": system_name},
    )


def who_manages(person_name: str) -> str:
    """Follow MANAGES lines (Eve manages Platform people)."""
    return _run_cypher(
        """
        MATCH (manager:Person)-[:MANAGES]->(p:Person)
        WHERE toLower(p.name) CONTAINS toLower($name)
           OR toLower(manager.name) CONTAINS toLower($name)
        RETURN manager.name AS manager, manager.role AS manager_role,
               p.name AS report, p.role AS report_role, p.team AS team
        """,
        {"name": person_name},
    )


def person_profile(person_name: str) -> str:
    """One person: role, team, projects, systems, manager."""
    return _run_cypher(
        """
        MATCH (p:Person)
        WHERE toLower(p.name) CONTAINS toLower($name)
        OPTIONAL MATCH (p)-[:WORKS_ON]->(proj:Project)
        OPTIONAL MATCH (proj)-[:USES]->(s:System)
        OPTIONAL MATCH (m:Person)-[:MANAGES]->(p)
        RETURN p.name AS name, p.role AS role, p.team AS team,
               collect(DISTINCT proj.name) AS projects,
               collect(DISTINCT s.name) AS systems,
               collect(DISTINCT m.name) AS managers
        """,
        {"name": person_name},
    )


def list_company() -> str:
    """Survey the company brain: people, work, knowledge, history."""
    people = _run_cypher(
        "MATCH (p:Person) RETURN p.name, p.role, p.team ORDER BY p.name"
    )
    projects = _run_cypher(
        "MATCH (proj:Project) RETURN proj.name, proj.status, proj.description ORDER BY proj.name"
    )
    systems = _run_cypher(
        "MATCH (s:System) RETURN s.name, s.type ORDER BY s.name"
    )
    docs = _run_cypher("MATCH (d:Document) RETURN d.title, d.kind")
    decisions = _run_cypher("MATCH (c:Decision) RETURN c.title, c.why")
    incidents = _run_cypher(
        "MATCH (i:Incident) RETURN i.id, i.title, i.severity, i.status"
    )
    return (
        "PEOPLE:\n" + people
        + "\n\nPROJECTS:\n" + projects
        + "\n\nSYSTEMS:\n" + systems
        + "\n\nDOCUMENTS:\n" + docs
        + "\n\nDECISIONS:\n" + decisions
        + "\n\nINCIDENTS:\n" + incidents
    )


def related_knowledge(topic: str) -> str:
    """Docs, decisions, and past incidents tied to a name (Track 3)."""
    return _run_cypher(
        """
        MATCH (n)
        WHERE (n:System OR n:Project OR n:Person)
          AND toLower(n.name) CONTAINS toLower($topic)
        OPTIONAL MATCH (d:Document)-[:ABOUT]->(n)
        OPTIONAL MATCH (c:Decision)-[:AFFECTS]->(n)
        OPTIONAL MATCH (i:Incident)-[:HIT]->(n)
        RETURN labels(n)[0] AS kind, n.name AS name,
               collect(DISTINCT d.title) AS documents,
               collect(DISTINCT c.title) AS decisions,
               collect(DISTINCT i.id + ' ' + coalesce(i.title, '')) AS incidents
        """,
        {"topic": topic},
    )


def who_to_page(system_name: str) -> str:
    """On-call chain: system → project → person → manager."""
    return _run_cypher(
        """
        MATCH (p:Person)-[:WORKS_ON]->(proj:Project)-[:USES]->(s:System)
        WHERE toLower(s.name) CONTAINS toLower($name)
        OPTIONAL MATCH (m:Person)-[:MANAGES]->(p)
        RETURN s.name AS system, proj.name AS project,
               p.name AS engineer, p.role AS role,
               coalesce(m.name, '(no manager in graph)') AS page_manager
        """,
        {"name": system_name},
    )


def post_agent_note(session_id: str, agent: str, note: str) -> str:
    """
    Track 2 coordination: agents share a blackboard IN THE GRAPH.
    Not a Python variable — if another agent wakes up later, the note is still there.
    """
    graph = get_connection()
    graph.query(
        """
        MERGE (s:Session {id: $sid})
        MERGE (s)-[:HAS_BLACKBOARD]->(b:Blackboard {id: $sid})
        CREATE (b)-[:HAS_NOTE]->(n:AgentNote {
            agent: $agent,
            note: $note,
            written_at: $when
        })
        """,
        {
            "sid": session_id,
            "agent": agent,
            "note": note[:1500],
            "when": datetime.now().isoformat(timespec="seconds"),
        },
    )
    return "noted"


def read_blackboard(session_id: str) -> str:
    return _run_cypher(
        """
        MATCH (s:Session {id: $sid})-[:HAS_BLACKBOARD]->(:Blackboard)-[:HAS_NOTE]->(n:AgentNote)
        RETURN n.written_at, n.agent, n.note
        ORDER BY n.written_at DESC
        LIMIT 12
        """,
        {"sid": session_id},
    )


def investigate_outage(system_name: str) -> str:
    """One button / one tool: blast radius + who to page + history."""
    return (
        "=== BLAST RADIUS ===\n"
        + impact_if_system_down(system_name)
        + "\n\n=== WHO TO PAGE ===\n"
        + who_to_page(system_name)
        + "\n\n=== DOCS / DECISIONS / PAST INCIDENTS ===\n"
        + related_knowledge(system_name)
    )


def recall_memories(session_id: str) -> str:
    """
    Track 2: read past Q&A stored as Memory bubbles on this session.
    Like opening an old notebook instead of starting from a blank brain.
    """
    return _run_cypher(
        """
        MATCH (s:Session {id: $sid})-[:HAS_MEMORY]->(m:Memory)
        RETURN m.asked_at, m.question, m.answer
        ORDER BY m.asked_at DESC
        LIMIT 8
        """,
        {"sid": session_id},
    )


def save_memory(session_id: str, question: str, answer: str) -> None:
    """Write this chat turn into the graph so it survives closing the tab."""
    graph = get_connection()
    graph.query(
        """
        MERGE (s:Session {id: $sid})
        CREATE (s)-[:HAS_MEMORY]->(m:Memory {
            question: $q,
            answer: $a,
            asked_at: $when
        })
        """,
        {
            "sid": session_id,
            "q": question,
            "a": answer[:2000],
            "when": datetime.now().isoformat(timespec="seconds"),
        },
    )


# Map tool name -> Python function
TOOL_FUNCTIONS = {
    "who_works_on_project": who_works_on_project,
    "who_knows_system": who_knows_system,
    "impact_if_system_down": impact_if_system_down,
    "who_manages": who_manages,
    "person_profile": person_profile,
    "list_company": list_company,
    "recall_memories": recall_memories,
    "related_knowledge": related_knowledge,
    "who_to_page": who_to_page,
    "investigate_outage": investigate_outage,
    "read_blackboard": read_blackboard,
}

# Describe tools to Gemini in a form it understands (function calling)
GEMINI_TOOLS = [
    genai.protos.Tool(
        function_declarations=[
            genai.protos.FunctionDeclaration(
                name="who_works_on_project",
                description="Who works on a project? Use for questions about a project team.",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "project_name": genai.protos.Schema(type=genai.protos.Type.STRING),
                    },
                    required=["project_name"],
                ),
            ),
            genai.protos.FunctionDeclaration(
                name="who_knows_system",
                description=(
                    "Who is connected to a software system (PostgreSQL, Redis, Kafka, PyTorch) "
                    "by working on a project that USES that system? Multi-hop graph lookup."
                ),
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "system_name": genai.protos.Schema(type=genai.protos.Type.STRING),
                    },
                    required=["system_name"],
                ),
            ),
            genai.protos.FunctionDeclaration(
                name="impact_if_system_down",
                description="If a system goes down, which projects and people are affected?",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "system_name": genai.protos.Schema(type=genai.protos.Type.STRING),
                    },
                    required=["system_name"],
                ),
            ),
            genai.protos.FunctionDeclaration(
                name="who_manages",
                description="Who manages whom? Pass a person name.",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "person_name": genai.protos.Schema(type=genai.protos.Type.STRING),
                    },
                    required=["person_name"],
                ),
            ),
            genai.protos.FunctionDeclaration(
                name="person_profile",
                description="Full profile for one employee: role, team, projects, systems, manager.",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "person_name": genai.protos.Schema(type=genai.protos.Type.STRING),
                    },
                    required=["person_name"],
                ),
            ),
            genai.protos.FunctionDeclaration(
                name="list_company",
                description="List every person, project, and system in the company graph.",
                parameters=genai.protos.Schema(type=genai.protos.Type.OBJECT, properties={}),
            ),
            genai.protos.FunctionDeclaration(
                name="recall_memories",
                description="Load past questions and answers from this chat session stored in the graph.",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "session_id": genai.protos.Schema(type=genai.protos.Type.STRING),
                    },
                    required=["session_id"],
                ),
            ),
            genai.protos.FunctionDeclaration(
                name="related_knowledge",
                description="Documents, decisions, and past incidents about a person, project, or system.",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "topic": genai.protos.Schema(type=genai.protos.Type.STRING),
                    },
                    required=["topic"],
                ),
            ),
            genai.protos.FunctionDeclaration(
                name="who_to_page",
                description="Who to call if a system is down: engineers and their managers.",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "system_name": genai.protos.Schema(type=genai.protos.Type.STRING),
                    },
                    required=["system_name"],
                ),
            ),
            genai.protos.FunctionDeclaration(
                name="investigate_outage",
                description="Full outage investigation for a system: blast radius, paging, docs, decisions, incidents.",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "system_name": genai.protos.Schema(type=genai.protos.Type.STRING),
                    },
                    required=["system_name"],
                ),
            ),
            genai.protos.FunctionDeclaration(
                name="read_blackboard",
                description="Read notes other OrgMind agents already wrote on the shared graph blackboard.",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "session_id": genai.protos.Schema(type=genai.protos.Type.STRING),
                    },
                    required=["session_id"],
                ),
            ),
        ]
    )
]

SYSTEM_INSTRUCTIONS = """
You are OrgMind, a company-brain made of cooperating agents on a graph.

Rules:
- Never invent people, projects, systems, docs, decisions, or incidents.
- MUST call graph tools before answering.
- Always name the PATH in the graph (Person-WORKS_ON->Project-USES->System, or Decision-AFFECTS->System).
- Outages: call investigate_outage.
- "Why did we..." questions: related_knowledge.
- Follow-ups / "what did I ask": recall_memories and read_blackboard.
- If tools return no rows, say it is not in the graph.
- Write like a sharp staff engineer: short, sourced, useful.
"""



def _call_tool(name, args, session_id):
    """Run the Python function that matches the tool Gemini picked."""
    if name == "list_company":
        return list_company()
    if name == "recall_memories":
        return recall_memories(session_id)
    if name == "read_blackboard":
        return read_blackboard(session_id)
    fn = TOOL_FUNCTIONS.get(name)
    if not fn:
        return f"Unknown tool: {name}"
    return fn(**args)


# model name -> time (seconds) when it may be used again
_cooling = {}


def _cool_down(name, error, seconds=None):
    """Mark a model as resting. Google tells us how long: 'retry in 17s'."""
    if seconds is None and "PerDay" in str(error):
        seconds = 6 * 3600          # daily quota used up: rest for hours
    if seconds is None:
        match = re.search(r"retry in (\d+(?:\.\d+)?)s", str(error))
        seconds = float(match.group(1)) + 1 if match else 30
    _cooling[name] = time.time() + seconds


def _pick_model():
    """First model in our list that is not resting."""
    now = time.time()
    ready = [n for n in MODEL_CANDIDATES if _cooling.get(n, 0) <= now]
    if ready:
        return ready[0]
    # Everyone is resting: wait for the one that recovers first
    soonest = min(MODEL_CANDIDATES, key=lambda n: _cooling[n])
    time.sleep(min(_cooling[soonest] - now, 40))
    return soonest


def _with_fallback(work):
    """Run work(model_name). If that model is limited, rest it and try the next."""
    last_error = None
    for _ in range(len(MODEL_CANDIDATES) + 1):
        name = _pick_model()
        try:
            return work(name)
        except ResourceExhausted as error:      # 429: out of quota
            _cool_down(name, error)
            last_error = error
        except NotFound as error:               # model name not on this key
            _cool_down(name, error, seconds=3600)
            last_error = error
    raise last_error


def _ask_with_model(name, question, session_id):
    """One full turn using ONE specific model."""
    model = genai.GenerativeModel(
        model_name=name,
        tools=GEMINI_TOOLS,
        system_instruction=SYSTEM_INSTRUCTIONS,
    )
    evidence = []
    chat = model.start_chat()
    response = chat.send_message(
        f"Session id: {session_id}\n"
        f"User question: {question}\n"
        "Look up facts with tools before answering."
    )

    for _ in range(6):
        function_calls = []
        for candidate in response.candidates:
            for part in candidate.content.parts:
                fc = getattr(part, "function_call", None)
                if fc and getattr(fc, "name", None):
                    function_calls.append(fc)
        if not function_calls:
            break

        tool_parts = []
        for fc in function_calls:
            args = {k: v for k, v in fc.args.items()} if fc.args else {}
            result = _call_tool(fc.name, args, session_id)
            evidence.append({"tool": fc.name, "args": args, "graph_result": result})
            tool_parts.append(
                genai.protos.Part(
                    function_response=genai.protos.FunctionResponse(
                        name=fc.name, response={"result": result}
                    )
                )
            )
        response = chat.send_message(tool_parts)

    answer = (response.text or "").strip()
    if not answer:
        answer = "I looked at the graph but could not form a sentence. Try asking again."

    if not evidence:
        evidence.append(
            {"tool": "list_company (fallback)", "args": {}, "graph_result": list_company()}
        )
        answer += "\n\n(I also loaded the full company graph so this is grounded in FalkorDB.)"

    save_memory(session_id, question, answer)
    evidence.append(
        {"tool": "save_memory", "args": {"session_id": session_id}, "graph_result": "stored in graph"}
    )
    return answer, evidence, name


def ask_orgmind(question: str, session_id: str):
    """Same as before, but hops to the next model if one is out of quota."""
    return _with_fallback(lambda name: _ask_with_model(name, question, session_id))


def run_war_room(system_name: str, session_id: str):
    """Three agents write to the graph blackboard, then ONE Gemini call writes the briefing."""
    scout = impact_if_system_down(system_name)
    librarian = related_knowledge(system_name)
    dispatcher = who_to_page(system_name)
    post_agent_note(session_id, "Scout", scout)
    post_agent_note(session_id, "Librarian", librarian)
    post_agent_note(session_id, "Dispatcher", dispatcher)

    prompt = (
        f"Live outage of {system_name}. Write a short incident briefing "
        "using ONLY the three agent notes below. Name the graph paths. "
        "If something is missing, say it is not in the graph.\n\n"
        f"SCOUT (blast radius):\n{scout}\n\n"
        f"LIBRARIAN (docs, decisions, incidents):\n{librarian}\n\n"
        f"DISPATCHER (who to page):\n{dispatcher}"
    )

    def work(name):
        model = genai.GenerativeModel(
            model_name=name,
            system_instruction="You are OrgMind. Write only from the notes you are given. Never invent facts.",
        )
        return model.generate_content(prompt).text.strip(), name

    briefing, model_name = _with_fallback(work)
    return {
        "scout": scout,
        "librarian": librarian,
        "dispatcher": dispatcher,
        "briefing": briefing,
        "evidence": [],
        "model_name": model_name,
    }