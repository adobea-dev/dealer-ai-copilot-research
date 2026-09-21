"""Preflight checks for System C before any Gemini quota is used."""

from __future__ import annotations

import importlib
import os

from dotenv import load_dotenv
from neo4j import GraphDatabase


load_dotenv()


def check_import(module: str) -> None:
    importlib.import_module(module)
    print(f"[PASS] import {module}")


def main() -> None:
    print("=" * 70)
    print("SYSTEM C PREFLIGHT")
    print("=" * 70)

    for module in [
        "google.adk",
        "mcp",
        "neo4j",
        "neo4j_mcp_server",
        "matplotlib",
    ]:
        check_import(module)

    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise EnvironmentError("GEMINI_API_KEY is missing.")
    print("[PASS] GEMINI_API_KEY is configured (value hidden).")

    neo4j_password = os.getenv("NEO4J_PASSWORD")
    if not neo4j_password:
        raise EnvironmentError("NEO4J_PASSWORD is missing.")

    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    username = os.getenv("NEO4J_USERNAME", "neo4j")
    database = os.getenv("NEO4J_DATABASE", "neo4j")

    driver = GraphDatabase.driver(
        uri,
        auth=(username, neo4j_password),
    )

    try:
        driver.verify_connectivity()
        print(f"[PASS] Neo4j connectivity: {uri}")

        with driver.session(database=database) as session:
            metrics = session.run(
                "MATCH (m:Metric) RETURN count(m) AS count"
            ).single()["count"]
            stages = session.run(
                "MATCH (s:FunnelStage) RETURN count(s) AS count"
            ).single()["count"]

        if metrics == 0 or stages == 0:
            raise RuntimeError(
                "Neo4j is reachable but semantic graph is not initialized. "
                "Run python -m scripts.initialize_knowledge_graph"
            )

        print(f"[PASS] Knowledge graph metrics: {metrics}")
        print(f"[PASS] Funnel stages: {stages}")

    finally:
        driver.close()

    from src.systems.agentic_analytics import AgenticAnalyticsSystem

    system = AgenticAnalyticsSystem()
    print(f"[PASS] System C import/model: {system.model}")

    print()
    print("[PASS] System C preflight completed without calling Gemini.")


if __name__ == "__main__":
    main()
