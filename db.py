"""
db.py - Database Connection and Graph Setup
===========================================
This file does 2 things:
1. Connects Python to your FalkorDB graph database
2. Creates the initial graph structure (nodes and relationships)

WHAT IS A GRAPH DATABASE? (Simple explanation)
---------------------------------------------
Imagine a mind map:
- Each "bubble" in the mind map = a NODE (e.g., a Person, a Project)
- Each "line" connecting bubbles = a RELATIONSHIP (e.g., WORKS_ON, MANAGES)

FalkorDB stores data exactly like this mind map!
"""

import os
from dotenv import load_dotenv
from falkordb import FalkorDB

# Load all the secret keys from our .env file
load_dotenv()

_graph = None

def get_connection():
    """Connect once, then reuse the same connection."""
    global _graph
    if _graph is None:
        options = {
            "host": os.getenv("FALKORDB_HOST", "localhost"),
            "port": int(os.getenv("FALKORDB_PORT", "6379")),
        }
        username = os.getenv("FALKORDB_USERNAME") or None
        password = os.getenv("FALKORDB_PASSWORD") or None
        if username:
            options["username"] = username
        if password:
            options["password"] = password
        _graph = FalkorDB(**options).select_graph("orgmind")
    return _graph


def setup_graph():
    """
    Create the initial data in our graph.
    
    We'll create:
    - People (employees)
    - Projects
    - Systems/tools they use
    - Relationships between them
    
    CYPHER QUERY EXPLAINED:
    -----------------------
    MERGE = "Create this node IF it doesn't already exist"
    (p:Person {name: 'Alice'}) = a node of type Person with name Alice
    -[:WORKS_ON]-> = a relationship called WORKS_ON pointing right
    """
    graph = get_connection()
    
    print("🔧 Setting up OrgMind graph database...")
    
    # --- CREATE PEOPLE (Nodes) ---
    # These are the employees in our pretend company
    people = [
        {"name": "Alice", "role": "Backend Engineer", "team": "Platform"},
        {"name": "Bob",   "role": "Frontend Engineer", "team": "Product"},
        {"name": "Carol", "role": "DevOps Engineer",   "team": "Platform"},
        {"name": "Dave",  "role": "Data Scientist",    "team": "AI"},
        {"name": "Eve",   "role": "Engineering Manager","team": "Platform"},
    ]
    
    for person in people:
        graph.query(
            "MERGE (p:Person {name: $name}) SET p.role = $role, p.team = $team",
            {"name": person["name"], "role": person["role"], "team": person["team"]}
        )
    
    print("✅ Created People nodes")
    
    # --- CREATE PROJECTS (Nodes) ---
    projects = [
        {"name": "AuthService",   "status": "active",   "description": "User authentication system"},
        {"name": "DataPipeline",  "status": "active",   "description": "ETL pipeline for analytics"},
        {"name": "MobileApp",     "status": "archived", "description": "iOS/Android mobile app"},
        {"name": "AIRecommender", "status": "active",   "description": "ML recommendation engine"},
    ]
    
    for project in projects:
        graph.query(
            "MERGE (proj:Project {name: $name}) SET proj.status = $status, proj.description = $description",
            {"name": project["name"], "status": project["status"], "description": project["description"]}
        )
    
    print("✅ Created Project nodes")
    
    # --- CREATE SYSTEMS (Nodes) ---
    systems = [
        {"name": "PostgreSQL", "type": "Database"},
        {"name": "Redis",      "type": "Cache"},
        {"name": "Kafka",      "type": "Message Queue"},
        {"name": "PyTorch",    "type": "ML Framework"},
    ]
    
    for system in systems:
        graph.query(
            "MERGE (s:System {name: $name}) SET s.type = $type",
            {"name": system["name"], "type": system["type"]}
        )
    
    print("✅ Created System nodes")
    
    # --- CREATE RELATIONSHIPS ---
    # Now we connect people to projects (who works on what)
    
    work_relations = [
        ("Alice", "AuthService"),
        ("Alice", "DataPipeline"),
        ("Bob",   "MobileApp"),
        ("Bob",   "AIRecommender"),
        ("Carol", "DataPipeline"),
        ("Dave",  "AIRecommender"),
        ("Dave",  "DataPipeline"),
    ]
    
    for person, project in work_relations:
        graph.query(
            """
            MATCH (p:Person {name: $person})
            MATCH (proj:Project {name: $project})
            MERGE (p)-[:WORKS_ON]->(proj)
            """,
            {"person": person, "project": project}
        )
    
    print("✅ Created WORKS_ON relationships")
    
    # Eve manages everyone on Platform team
    graph.query(
        """
        MATCH (e:Person {name: 'Eve'})
        MATCH (p:Person) WHERE p.team = 'Platform' AND p.name <> 'Eve'
        MERGE (e)-[:MANAGES]->(p)
        """
    )
    
    print("✅ Created MANAGES relationships")
    
    # Connect projects to the systems they use
    project_systems = [
        ("AuthService",   "PostgreSQL"),
        ("AuthService",   "Redis"),
        ("DataPipeline",  "Kafka"),
        ("DataPipeline",  "PostgreSQL"),
        ("AIRecommender", "PyTorch"),
        ("AIRecommender", "PostgreSQL"),
    ]
    
    for project, system in project_systems:
        graph.query(
            """
            MATCH (proj:Project {name: $project})
            MATCH (s:System {name: $system})
            MERGE (proj)-[:USES]->(s)
            """,
            {"project": project, "system": system}
        )
    
    print("✅ Created USES relationships (Projects → Systems)")
    enrich_graph(graph)
    print("\n🎉 Graph database setup complete!")
    print("   OrgMind now has people, projects, systems, docs, decisions, and incidents.")


def enrich_graph(graph):
    """
    Make the company brain feel real — not a tiny toy.

    Extra bubbles:
    - More people (PM, SRE, security)
    - Documents (runbooks, RFCs)
    - Decisions (why we did something)
    - Incidents (what broke before)

    This is Track 3: a Company Brain judges can click through.
    """
    extra_people = [
        {"name": "Frank", "role": "Product Manager", "team": "Product"},
        {"name": "Grace", "role": "SRE", "team": "Platform"},
        {"name": "Hank", "role": "Security Engineer", "team": "Security"},
    ]
    for person in extra_people:
        graph.query(
            "MERGE (p:Person {name: $name}) SET p.role = $role, p.team = $team",
            person,
        )

    extra_projects = [
        {"name": "Payments", "status": "active", "description": "Checkout and billing"},
        {"name": "Observability", "status": "active", "description": "Metrics, logs, paging"},
    ]
    for project in extra_projects:
        graph.query(
            "MERGE (proj:Project {name: $name}) SET proj.status = $status, proj.description = $description",
            project,
        )

    extra_systems = [
        {"name": "PagerDuty", "type": "Ops"},
        {"name": "S3", "type": "Storage"},
    ]
    for system in extra_systems:
        graph.query(
            "MERGE (s:System {name: $name}) SET s.type = $type",
            system,
        )

    extra_work = [
        ("Frank", "MobileApp"),
        ("Frank", "Payments"),
        ("Grace", "Observability"),
        ("Grace", "DataPipeline"),
        ("Grace", "AuthService"),
        ("Hank", "AuthService"),
        ("Hank", "Payments"),
        ("Alice", "Payments"),
        ("Carol", "Observability"),
    ]
    for person, project in extra_work:
        graph.query(
            """
            MATCH (p:Person {name: $person})
            MATCH (proj:Project {name: $project})
            MERGE (p)-[:WORKS_ON]->(proj)
            """,
            {"person": person, "project": project},
        )

    extra_uses = [
        ("Payments", "PostgreSQL"),
        ("Payments", "Redis"),
        ("Payments", "Kafka"),
        ("Payments", "S3"),
        ("Observability", "PagerDuty"),
        ("Observability", "Kafka"),
    ]
    for project, system in extra_uses:
        graph.query(
            """
            MATCH (proj:Project {name: $project})
            MATCH (s:System {name: $name})
            MERGE (proj)-[:USES]->(s)
            """,
            {"project": project, "name": system},
        )

    graph.query(
        """
        MATCH (e:Person {name: 'Eve'})
        MATCH (p:Person) WHERE p.team = 'Platform' AND p.name <> 'Eve'
        MERGE (e)-[:MANAGES]->(p)
        """
    )

    docs = [
        {
            "title": "RFC-214 Auth sessions in Redis",
            "kind": "RFC",
            "author": "Alice",
            "about": ["AuthService", "Redis"],
        },
        {
            "title": "PostgreSQL on-call runbook",
            "kind": "runbook",
            "author": "Carol",
            "about": ["PostgreSQL", "DataPipeline"],
        },
        {
            "title": "Payments threat model",
            "kind": "security",
            "author": "Hank",
            "about": ["Payments", "AuthService"],
        },
    ]
    for doc in docs:
        graph.query(
            """
            MERGE (d:Document {title: $title})
            SET d.kind = $kind
            WITH d
            MATCH (p:Person {name: $author})
            MERGE (p)-[:AUTHORED]->(d)
            """,
            {"title": doc["title"], "kind": doc["kind"], "author": doc["author"]},
        )
        for thing in doc["about"]:
            graph.query(
                """
                MATCH (d:Document {title: $title})
                OPTIONAL MATCH (proj:Project {name: $thing})
                OPTIONAL MATCH (s:System {name: $thing})
                FOREACH (_ IN CASE WHEN proj IS NULL THEN [] ELSE [1] END |
                    MERGE (d)-[:ABOUT]->(proj)
                )
                FOREACH (_ IN CASE WHEN s IS NULL THEN [] ELSE [1] END |
                    MERGE (d)-[:ABOUT]->(s)
                )
                """,
                {"title": doc["title"], "thing": thing},
            )

    decisions = [
        {
            "title": "Keep login sessions in Redis, not PostgreSQL",
            "why": "Postgres was locking under session load. RFC-214.",
            "owner": "Eve",
            "about": ["AuthService", "Redis", "PostgreSQL"],
        },
        {
            "title": "Kafka is the source of truth for the pipeline",
            "why": "Replayable events beat a single DB write path.",
            "owner": "Carol",
            "about": ["DataPipeline", "Kafka"],
        },
    ]
    for decision in decisions:
        graph.query(
            """
            MERGE (c:Decision {title: $title})
            SET c.why = $why
            WITH c
            MATCH (p:Person {name: $owner})
            MERGE (p)-[:DECIDED]->(c)
            """,
            {
                "title": decision["title"],
                "why": decision["why"],
                "owner": decision["owner"],
            },
        )
        for thing in decision["about"]:
            graph.query(
                """
                MATCH (c:Decision {title: $title})
                OPTIONAL MATCH (proj:Project {name: $thing})
                OPTIONAL MATCH (s:System {name: $thing})
                FOREACH (_ IN CASE WHEN proj IS NULL THEN [] ELSE [1] END |
                    MERGE (c)-[:AFFECTS]->(proj)
                )
                FOREACH (_ IN CASE WHEN s IS NULL THEN [] ELSE [1] END |
                    MERGE (c)-[:AFFECTS]->(s)
                )
                """,
                {"title": decision["title"], "thing": thing},
            )

    incidents = [
        {
            "id": "INC-441",
            "title": "Redis timeouts during login spike",
            "severity": "high",
            "status": "resolved",
            "owner": "Alice",
            "about": ["Redis", "AuthService"],
        },
        {
            "id": "INC-502",
            "title": "PostgreSQL lock pileup in analytics load",
            "severity": "medium",
            "status": "resolved",
            "owner": "Carol",
            "about": ["PostgreSQL", "DataPipeline"],
        },
    ]
    for incident in incidents:
        graph.query(
            """
            MERGE (i:Incident {id: $id})
            SET i.title = $title, i.severity = $severity, i.status = $status
            WITH i
            MATCH (p:Person {name: $owner})
            MERGE (p)-[:ACKNOWLEDGED]->(i)
            """,
            {
                "id": incident["id"],
                "title": incident["title"],
                "severity": incident["severity"],
                "status": incident["status"],
                "owner": incident["owner"],
            },
        )
        for thing in incident["about"]:
            graph.query(
                """
                MATCH (i:Incident {id: $id})
                OPTIONAL MATCH (proj:Project {name: $thing})
                OPTIONAL MATCH (s:System {name: $thing})
                FOREACH (_ IN CASE WHEN proj IS NULL THEN [] ELSE [1] END |
                    MERGE (i)-[:HIT]->(proj)
                )
                FOREACH (_ IN CASE WHEN s IS NULL THEN [] ELSE [1] END |
                    MERGE (i)-[:HIT]->(s)
                )
                """,
                {"id": incident["id"], "thing": thing},
            )

    print("✅ Enriched graph: extra people, docs, decisions, incidents")


def test_connection():
    """Quick test to verify the database connection works."""
    try:
        graph = get_connection()
        result = graph.query("RETURN 'Connection successful!' AS message")
        print(result.result_set[0][0])
        return True
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False


# This runs ONLY when you directly run this file (python db.py)
# It will NOT run when other files import from this file
if __name__ == "__main__":
    print("🔌 Testing connection to FalkorDB...")
    if test_connection():
        setup_graph()
