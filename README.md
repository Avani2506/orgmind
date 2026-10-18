# OrgMind: a company brain that runs on a graph

Built for **Graph Hacks: Context for AI Agents** (WeMakeDevs x FalkorDB).

- **Live demo:** Not deployed. OrgMind depends on a FalkorDB instance running alongside the app, so it runs locally with Docker (FalkorDB) and Streamlit. Complete setup steps are in the "Run it locally" section below, and the demo video shows the working project end to end.
- **Demo video:** https://www.loom.com/share/949f45c0e8d34e3cb1a168014620c447
- **Tracks entered:** Agents That Act on Connected Data, Agent Memory and Coordination, Company Brain

OrgMind answers questions about a company (who works on what, what breaks if a system goes down, why a decision was made) by walking a FalkorDB graph. The AI is not allowed to guess. It must call graph tools, and every answer shows the lookups it used. If FalkorDB is switched off, OrgMind cannot answer, which is the point: the graph is what the product runs on.

## Try it in two minutes

1. Open the live demo and enter any username. Your username is your memory key: come back with the same name and OrgMind remembers your earlier questions.
2. In **Chat**, click "Who knows about PostgreSQL?" and open **Graph proof** to see the path it followed.
3. Ask "What did I ask you last time?" The answer comes from Memory nodes stored in FalkorDB.
4. In **Living graph**, click a node to fade everything it is not connected to.
5. In **War room**, pick Redis and click **Investigate outage**. Three agents write to a shared blackboard in the graph, then you get a briefing and a picture of the blast radius.

## Run it locally

You need Python 3.10+, Git, Docker Desktop, and a free Gemini API key from https://aistudio.google.com/apikey.

**1. Start FalkorDB.** On Windows, Docker Desktop needs WSL: if it complains, run `wsl --install` in an administrator PowerShell, restart, then open Docker Desktop and wait until it says it is running.

```bash
docker run -d --name orgmind-falkordb -p 6379:6379 falkordb/falkordb:latest
```

If the container already exists, run `docker start orgmind-falkordb`. `docker ps` should list it as Up.

**2. Get the code.**

```bash
git clone https://github.com/Avani2506/orgmind.git
cd orgmind
pip install -r requirements.txt
```

**3. Add your key.** Copy `.env.example` to `.env` and replace `paste-your-key-here` with your Gemini key.

**4. Build the sample company graph.**

```bash
python db.py
```

**5. Start the app.**

```bash
python -m streamlit run app.py
```

Open http://localhost:8501.

**Troubleshooting**

- "FalkorDB is not reachable": start Docker Desktop, then `docker start orgmind-falkordb`.
- Gemini error 429: the free quota is used up for a moment. Wait a minute and ask again.
- `streamlit` not recognized: use `python -m streamlit run app.py`.

## Graph data model

Nodes: `Person`, `Project`, `System`, `Document`, `Decision`, `Incident`, plus `Session`, `Memory`, `Blackboard`, `AgentNote` for memory.

```
(Person)-[:WORKS_ON]->(Project)-[:USES]->(System)
(Person)-[:MANAGES]->(Person)
(Person)-[:AUTHORED]->(Document)-[:ABOUT]->(Project|System)
(Person)-[:DECIDED]->(Decision)-[:AFFECTS]->(Project|System)
(Person)-[:ACKNOWLEDGED]->(Incident)-[:HIT]->(Project|System)
(Session)-[:HAS_MEMORY]->(Memory)
(Session)-[:HAS_BLACKBOARD]->(Blackboard)-[:HAS_NOTE]->(AgentNote)
```

All data is synthetic (a made-up company).

## Key Cypher queries

Who is connected to a system (multi-hop):

```cypher
MATCH (p:Person)-[:WORKS_ON]->(proj:Project)-[:USES]->(s:System)
WHERE toLower(s.name) CONTAINS toLower($name)
RETURN p.name, p.role, proj.name, s.name
```

Who to page if a system is down:

```cypher
MATCH (p:Person)-[:WORKS_ON]->(proj:Project)-[:USES]->(s:System)
WHERE toLower(s.name) CONTAINS toLower($name)
OPTIONAL MATCH (m:Person)-[:MANAGES]->(p)
RETURN s.name, proj.name, p.name, coalesce(m.name, '(no manager in graph)')
```

Decisions, documents and incidents tied to a topic:

```cypher
MATCH (n) WHERE (n:System OR n:Project OR n:Person) AND toLower(n.name) CONTAINS toLower($topic)
OPTIONAL MATCH (d:Document)-[:ABOUT]->(n)
OPTIONAL MATCH (c:Decision)-[:AFFECTS]->(n)
OPTIONAL MATCH (i:Incident)-[:HIT]->(n)
RETURN n.name, collect(DISTINCT d.title), collect(DISTINCT c.title), collect(DISTINCT i.id)
```

Save and recall memory:

```cypher
MERGE (s:Session {id: $sid})
CREATE (s)-[:HAS_MEMORY]->(m:Memory {question: $q, answer: $a, asked_at: $when})
```

```cypher
MATCH (:Session {id: $sid})-[:HAS_MEMORY]->(m:Memory)
RETURN m.asked_at, m.question, m.answer ORDER BY m.asked_at DESC LIMIT 8
```

Agents share notes on a blackboard in the graph:

```cypher
MERGE (s:Session {id: $sid})
MERGE (s)-[:HAS_BLACKBOARD]->(b:Blackboard {id: $sid})
CREATE (b)-[:HAS_NOTE]->(n:AgentNote {agent: $agent, note: $note, written_at: $when})
```

## AI disclosure

Built with AI coding assistants. At runtime the app uses Google Gemini to choose graph tools and write answers from the rows they return.

## Rights

Copyright (c) 2026 Avani.Vibhute. All rights reserved.
