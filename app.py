"""
app.py - OrgMind's face (v2: a proper site)
===========================================
Pages
-----
0. Sign-in   - your name is your memory key, so history survives across days
1. Chat      - ask the company, with clickable starter questions
2. Graph     - filter, search, and click through the live mind-map
3. War room  - three agents investigate an outage, then you see the blast radius
4. Memory    - everything this user has taught the graph (Memory + AgentNote nodes)

Everything shown comes from FalkorDB. If the database is off, the app tells you how to start it.
"""

import html
import re
from collections import deque

import streamlit as st
import streamlit.components.v1 as components

from agent import ask_orgmind, list_company, run_war_room
from db import get_connection
from graph_view import COLORS, fetch_company_edges, vis_html

st.set_page_config(page_title="OrgMind", page_icon="🧠", layout="wide")

# ---------------------------------------------------------------------------
# LOOK AND FEEL
# Chart-paper canvas, ink-blue sidebar, teal for actions, and one dark "map table"
# panel (the graph) as the memorable thing. Everything else stays quiet.
# ---------------------------------------------------------------------------
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500..800&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

html, body, .stApp, [class*="css"] { font-family: 'IBM Plex Sans', system-ui, sans-serif; }
h1, h2, h3, .display { font-family: 'Bricolage Grotesque', 'IBM Plex Sans', sans-serif; letter-spacing: -0.02em; color: #14213D; }

.stApp {
  background-color: #EEF2F4;
  background-image: radial-gradient(#C9D3DA 1px, transparent 1px);
  background-size: 22px 22px;
}
footer, #MainMenu { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 2rem; max-width: 1280px; }

/* sidebar */
[data-testid="stSidebar"] { background: #14213D; }
[data-testid="stSidebar"] .stMarkdown *, [data-testid="stSidebar"] [data-testid="stCaptionContainer"] * { color: #D8E1E8 !important; }
[data-testid="stSidebar"] .brand { font-family: 'Bricolage Grotesque', sans-serif; font-size: 1.9rem; font-weight: 700; color: #FFFFFF !important; }
[data-testid="stSidebar"] .stButton button {
  background: transparent; color: #FFFFFF; border: 1px solid rgba(255,255,255,0.35); border-radius: 8px;
}
[data-testid="stSidebar"] .stButton button:hover { border-color: #F2B84B; color: #F2B84B; }

/* sign-in */
.hero-title { font-family: 'Bricolage Grotesque', sans-serif; font-weight: 700; font-size: 3.1rem; line-height: 1.05; color: #14213D; margin: 0 0 14px 0; }
.hero-copy { font-size: 1.08rem; line-height: 1.55; color: #3B4A63; max-width: 34em; margin-bottom: 22px; }

/* top strip */
.topline { display: flex; align-items: baseline; gap: 16px; margin-bottom: 4px; }
.topline h1 { margin: 0; font-size: 2.2rem; }
.topline p { margin: 0; color: #53627C; }
.stats { display: flex; gap: 10px; flex-wrap: wrap; margin: 12px 0 18px 0; }
.stat { background: #FFFFFF; border: 1px solid #D5DDE3; border-radius: 10px; padding: 8px 14px; display: flex; align-items: center; gap: 8px; }
.stat i { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.stat b { font-family: 'Bricolage Grotesque', sans-serif; font-size: 1.15rem; color: #14213D; }
.stat span { color: #53627C; font-size: 0.9rem; }

/* tabs */
.stTabs [data-baseweb="tab-list"] { gap: 6px; border-bottom: 1px solid #C9D3DA; }
.stTabs [data-baseweb="tab"] { height: 44px; padding: 0 16px; font-weight: 500; color: #53627C; }
.stTabs [aria-selected="true"] { color: #0F8B8D; }
.stTabs [data-baseweb="tab-highlight"] { background-color: #0F8B8D; }

/* buttons */
.stButton button, .stFormSubmitButton button { border-radius: 8px; font-weight: 500; }
.stButton button[kind="primary"], .stFormSubmitButton button[kind="primary"] { background: #0F8B8D; border: 0; color: #FFFFFF; }
.stButton button[kind="primary"]:hover, .stFormSubmitButton button[kind="primary"]:hover { background: #0B6E70; }
.starter button { text-align: left; background: #FFFFFF; border: 1px solid #C9D3DA; color: #14213D; min-height: 64px; line-height: 1.35; }
.starter button:hover { border-color: #0F8B8D; color: #0F8B8D; }

/* chat */
[data-testid="stChatMessage"] { background: #FFFFFF; border: 1px solid #D5DDE3; border-radius: 14px; padding: 14px 18px; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) { background: #14213D; border-color: #14213D; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) * { color: #FFFFFF; }

/* pills used in graph proof and cards */
.pill { display: inline-block; background: #E1F2F2; color: #0B6E70; border-radius: 999px; padding: 2px 10px; font-size: 0.82rem; font-weight: 600; margin-right: 6px; }
.pill.write { background: #FCEFD2; color: #8A5B00; }
.agent { border-radius: 10px; padding: 10px 14px; margin-bottom: 8px; color: #14213D; }
.agent b { font-family: 'Bricolage Grotesque', sans-serif; font-size: 1.1rem; }
.agent span { display: block; font-size: 0.85rem; opacity: 0.8; }
.agent.scout { background: #FCE3D3; }
.agent.librarian { background: #E4DEFF; }
.agent.dispatcher { background: #D4F1EE; }
.note { color: #53627C; font-size: 0.9rem; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# SMALL HELPERS (all of them ask FalkorDB, none of them guess)
# ---------------------------------------------------------------------------
def graph_rows(cypher, params=None):
    """Run a Cypher query and return rows, or [] if the database is unreachable."""
    try:
        return get_connection().query(cypher, params or {}).result_set or []
    except Exception:
        return []


def db_ok():
    try:
        get_connection().query("RETURN 1")
        return True
    except Exception:
        return False


@st.cache_data(ttl=20)
def company_counts():
    out = {}
    for label in ["Person", "Project", "System", "Document", "Decision", "Incident"]:
        rows = graph_rows(f"MATCH (n:{label}) RETURN count(n)")
        out[label] = rows[0][0] if rows else 0
    return out


@st.cache_data(ttl=20)
def company_edges():
    return fetch_company_edges()


def memory_count(session_id):
    rows = graph_rows(
        "MATCH (:Session {id: $sid})-[:HAS_MEMORY]->(m:Memory) RETURN count(m)",
        {"sid": session_id},
    )
    return rows[0][0] if rows else 0


def neighborhood(edges, name, hops=3):
    """Every edge within `hops` steps of a node, so the war room can draw the blast radius."""
    adj = {}
    for _lk, ln, _rel, _rk, rn in edges:
        adj.setdefault(str(ln), set()).add(str(rn))
        adj.setdefault(str(rn), set()).add(str(ln))
    start = [n for n in adj if n.lower() == name.lower()]
    seen = set(start)
    queue = deque((s, 0) for s in start)
    while queue:
        node, depth = queue.popleft()
        if depth == hops:
            continue
        for nxt in adj[node]:
            if nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, depth + 1))
    return [e for e in edges if str(e[1]) in seen and str(e[4]) in seen]


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def show_proof(evidence, expanded=False):
    """Show which graph lookups produced the answer."""
    if not evidence:
        return
    lookups = [e for e in evidence if e["tool"] != "save_memory"]
    label = f"Graph proof: {len(lookups)} lookup{'s' if len(lookups) != 1 else ''}"
    with st.expander(label, expanded=expanded):
        for item in evidence:
            if item["tool"] == "save_memory":
                st.markdown('<span class="pill write">saved to memory</span> this turn was written back to the graph', unsafe_allow_html=True)
                continue
            args = html.escape(str(item["args"]))
            st.markdown(f'<span class="pill">{html.escape(item["tool"])}</span><span class="note">{args}</span>', unsafe_allow_html=True)
            st.code(item["graph_result"], language=None)


# ---------------------------------------------------------------------------
# PAGE 0: SIGN-IN
# Why a name? Memory is stored under a session id. A random id changes every visit,
# so yesterday's memories become unreachable. A name gives a stable id.
# ---------------------------------------------------------------------------
def sign_in_page():
    left, right = st.columns([1, 1.1], gap="large")
    with left:
        st.markdown(
            '<div class="hero-title">Your company, as a map your AI has to read.</div>'
            '<div class="hero-copy">OrgMind answers from FalkorDB, not from guesses. '
            "Every answer shows the path it walked through people, projects and systems, "
            "and every question is saved to the graph under your name.</div>",
            unsafe_allow_html=True,
        )
        with st.form("signin"):
            name = st.text_input("Your name", placeholder="For example: avani")
            st.caption("Your name is your memory key. Come back with the same name and OrgMind remembers your earlier questions.")
            go = st.form_submit_button("Open OrgMind", type="primary")
        if go:
            slug = slugify(name)
            if len(slug) < 2:
                st.error("Enter at least two letters or numbers so your memory has a name to live under.")
            else:
                st.session_state.user = name.strip()
                st.session_state.session_id = slug
                st.session_state.messages = []
                st.session_state.war = None
                st.rerun()
    with right:
        try:
            components.html(vis_html(company_edges(), height=470), height=480)
        except Exception as error:
            st.error(f"The live graph could not load: {error}")


def db_down_banner():
    st.error(
        "FalkorDB is not reachable. Start Docker Desktop, then run `docker start orgmind-falkordb` "
        "in Command Prompt and reload this page."
    )


# ---------------------------------------------------------------------------
# STATE
# ---------------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []
if "war" not in st.session_state:
    st.session_state.war = None

if not db_ok():
    db_down_banner()
    st.stop()

if "user" not in st.session_state:
    sign_in_page()
    st.stop()

user = st.session_state.user
sid = st.session_state.session_id

# ---------------------------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown('<div class="brand">OrgMind</div>', unsafe_allow_html=True)
    st.caption("A company brain that runs on a graph")
    st.markdown(f"Signed in as **{html.escape(user)}**")
    st.caption(f"{memory_count(sid)} questions remembered in the graph")
    st.markdown("**How it meets the three tracks**")
    st.markdown(
        "Connected data: answers follow Person, Project and System links.  \n"
        "Memory: questions and agent notes are stored as nodes.  \n"
        "Company brain: documents, decisions and incidents hang off the same graph."
    )
    if st.button("Switch user"):
        for key in ("user", "session_id", "messages", "war", "pending"):
            st.session_state.pop(key, None)
        st.rerun()

# ---------------------------------------------------------------------------
# HEADER AND STATS (real counts from the graph)
# ---------------------------------------------------------------------------
counts = company_counts()
stat_html = "".join(
    f'<div class="stat"><i style="background:{COLORS[k]}"></i><b>{counts.get(k, 0)}</b><span>{label}</span></div>'
    for k, label in [
        ("Person", "people"),
        ("Project", "projects"),
        ("System", "systems"),
        ("Document", "documents"),
        ("Decision", "decisions"),
        ("Incident", "incidents"),
    ]
)
st.markdown(
    f'<div class="topline"><h1>OrgMind</h1><p>Hello, {html.escape(user)}. Ask anything about how the company fits together.</p></div>'
    f'<div class="stats">{stat_html}</div>',
    unsafe_allow_html=True,
)

chat_tab, graph_tab, war_tab, mem_tab = st.tabs(["Chat", "Living graph", "War room", "Memory"])

# ---------------------------------------------------------------------------
# CHAT
# ---------------------------------------------------------------------------
STARTERS = [
    "Who knows about PostgreSQL?",
    "Why are auth sessions in Redis?",
    "What breaks if Kafka dies?",
    "Who manages Alice, and what does she work on?",
]


def pick_starter(question):
    st.session_state.pending = question


with chat_tab:
    pending = st.session_state.pop("pending", None)

    if not st.session_state.messages and not pending:
        earlier = memory_count(sid)
        if earlier:
            st.info(f"Welcome back. {earlier} earlier question(s) are saved in the graph. Try asking: What did I ask you last time?")
        st.markdown("**Start with one of these**")
        cols = st.columns(2)
        for i, q in enumerate(STARTERS):
            with cols[i % 2]:
                st.markdown('<div class="starter">', unsafe_allow_html=True)
                st.button(q, key=f"starter{i}", on_click=pick_starter, args=(q,), use_container_width=True)
                st.markdown("</div>", unsafe_allow_html=True)

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("model"):
                st.caption(f"Answered by {msg['model']}")
            show_proof(msg.get("evidence"))

    typed = st.chat_input("Ask about people, systems, decisions or outages")
    question = typed or pending
    if question:
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            with st.spinner("Walking the graph..."):
                try:
                    answer, evidence, model_name = ask_orgmind(question, sid)
                except Exception as error:
                    answer = f"Something went wrong while talking to Gemini or FalkorDB:\n\n`{error}`"
                    evidence, model_name = [], None
            st.markdown(answer)
            if model_name:
                st.caption(f"Answered by {model_name}")
            show_proof(evidence, expanded=True)
        st.session_state.messages.append(
            {"role": "assistant", "content": answer, "evidence": evidence, "model": model_name}
        )

# ---------------------------------------------------------------------------
# LIVING GRAPH
# ---------------------------------------------------------------------------
with graph_tab:
    st.subheader("The company is the product")
    kinds = list(COLORS.keys())
    f1, f2 = st.columns([2, 1])
    chosen = f1.multiselect("Show these kinds of nodes", kinds, default=kinds)
    needle = f2.text_input("Find a node", placeholder="Try: Redis")
    edges = [e for e in company_edges() if e[0] in chosen and e[3] in chosen]
    if edges:
        components.html(vis_html(edges, highlight=needle, height=620), height=630)
        st.caption(f"{len(edges)} relationships loaded live from FalkorDB. Click any node to fade everything it is not connected to.")
    else:
        st.info("Nothing to draw. Pick at least two kinds of nodes, for example Person and Project.")

# ---------------------------------------------------------------------------
# WAR ROOM
# ---------------------------------------------------------------------------
with war_tab:
    st.subheader("Incident war room")
    st.write(
        "Pick a system that is down. Scout, Librarian and Dispatcher write notes to a shared blackboard "
        "stored in FalkorDB, then OrgMind briefs you and draws the blast radius."
    )
    system = st.radio("System that is down", ["PostgreSQL", "Redis", "Kafka", "PyTorch", "PagerDuty", "S3"], horizontal=True)
    if st.button("Investigate outage", type="primary"):
        with st.spinner("Three agents are reading the graph..."):
            try:
                result = run_war_room(system, sid)
                result["system"] = system
                st.session_state.war = result
            except Exception as error:
                st.session_state.war = {"error": str(error)}

    war = st.session_state.war
    if war and "error" in war:
        st.error(f"The war room hit a problem: {war['error']}")
    elif war:
        c1, c2, c3 = st.columns(3)
        c1.markdown('<div class="agent scout"><b>Scout</b><span>What else breaks</span></div>', unsafe_allow_html=True)
        c1.code(war["scout"], language=None)
        c2.markdown('<div class="agent librarian"><b>Librarian</b><span>Docs, decisions, past incidents</span></div>', unsafe_allow_html=True)
        c2.code(war["librarian"], language=None)
        c3.markdown('<div class="agent dispatcher"><b>Dispatcher</b><span>Who to page, and their manager</span></div>', unsafe_allow_html=True)
        c3.code(war["dispatcher"], language=None)

        with st.container(border=True):
            st.markdown(f"### Briefing: {war.get('system', 'outage')}")
            st.markdown(war["briefing"])

        blast = neighborhood(company_edges(), war.get("system", ""))
        if blast:
            st.markdown("**Blast radius** (three steps out from the failed system)")
            components.html(vis_html(blast, highlight=war.get("system"), height=480), height=490)

# ---------------------------------------------------------------------------
# MEMORY
# ---------------------------------------------------------------------------
with mem_tab:
    st.subheader(f"What OrgMind remembers about {user}")
    st.caption("Stored as Memory and AgentNote nodes. Close the tab, come back tomorrow with the same name, and they are still here.")
    m_col, b_col = st.columns(2, gap="large")

    with m_col:
        st.markdown("**Questions and answers**")
        memories = graph_rows(
            """
            MATCH (s:Session {id: $sid})-[:HAS_MEMORY]->(m:Memory)
            RETURN m.asked_at, m.question, m.answer
            ORDER BY m.asked_at DESC LIMIT 30
            """,
            {"sid": sid},
        )
        if not memories:
            st.info("Nothing saved yet. Ask a question in the Chat tab and it will appear here.")
        for asked_at, q, a in memories:
            with st.expander(str(q)[:90]):
                st.caption(str(asked_at))
                st.markdown(str(a))

    with b_col:
        st.markdown("**Agent blackboard**")
        notes = graph_rows(
            """
            MATCH (s:Session {id: $sid})-[:HAS_BLACKBOARD]->(:Blackboard)-[:HAS_NOTE]->(n:AgentNote)
            RETURN n.written_at, n.agent, n.note
            ORDER BY n.written_at DESC LIMIT 12
            """,
            {"sid": sid},
        )
        if not notes:
            st.info("No agent notes yet. Run an investigation in the War room.")
        for written_at, agent_name, note in notes:
            with st.expander(f"{agent_name}, {written_at}"):
                st.code(str(note), language=None)

    with st.expander("Raw company inventory"):
        if st.button("Load inventory"):
            st.code(list_company(), language=None)