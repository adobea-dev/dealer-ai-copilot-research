"""Initialize the Neo4j semantic knowledge graph for System C."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase


load_dotenv()

SEED_PATH = Path("knowledge_graph/seed.cypher")


def split_statements(text: str) -> list[str]:
    statements = []
    current = []

    for line in text.splitlines():
        stripped = line.strip()

        if not stripped or stripped.startswith("//"):
            continue

        current.append(line)

        if stripped.endswith(";"):
            statement = "\n".join(current).strip()
            statement = statement[:-1].strip()
            if statement:
                statements.append(statement)
            current = []

    if current:
        statements.append("\n".join(current).strip())

    return statements


def main() -> None:
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    username = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "")
    database = os.getenv("NEO4J_DATABASE", "neo4j")

    if not password:
        raise EnvironmentError("NEO4J_PASSWORD is not set in .env.")

    text = SEED_PATH.read_text(encoding="utf-8")
    statements = split_statements(text)

    driver = GraphDatabase.driver(
        uri,
        auth=(username, password),
    )

    try:
        driver.verify_connectivity()

        with driver.session(database=database) as session:
            for index, statement in enumerate(statements, start=1):
                session.run(statement).consume()
                print(f"[PASS] {index}/{len(statements)}")

            node_count = session.run(
                "MATCH (n) RETURN count(n) AS count"
            ).single()["count"]

            relationship_count = session.run(
                "MATCH ()-[r]->() RETURN count(r) AS count"
            ).single()["count"]

        print()
        print("=" * 70)
        print("KNOWLEDGE GRAPH INITIALIZED")
        print("=" * 70)
        print(f"Nodes:         {node_count}")
        print(f"Relationships: {relationship_count}")

    finally:
        driver.close()


if __name__ == "__main__":
    main()
