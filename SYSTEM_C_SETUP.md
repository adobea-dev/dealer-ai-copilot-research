# System C — MCP + Neo4j Knowledge Graph + ADK Agent

System C is the agentic condition of Dealer AI Copilot 2.0.

Architecture:

```text
Question
  -> deterministic input guard
  -> fresh per-task ADK session
  -> root analytics agent
       -> Neo4j semantic KG through MCP
       -> read-only PostgreSQL tool
       -> deterministic calculator
       -> deterministic visualization tool
  -> grounded synthesis
  -> PII redaction
  -> research log/evaluator
```

There is no persistent cross-task memory.

## 1. Python requirements

From the active `dealerai-env`:

```powershell
pip install "google-adk>=2.0.0,<3.0.0" mcp neo4j neo4j-mcp-server matplotlib python-dotenv
```

Add the same packages to the existing `requirements.txt`. Do not replace the
file.

## 2. Neo4j requirement

Use either:
- Neo4j Desktop / self-managed Neo4j; or
- Neo4j Aura.

For a local Neo4j instance, the official Neo4j MCP server expects APOC to be
available. If using Neo4j Desktop, install/enable the APOC plugin for the DB.

Default local connection used by this package:

```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=YOUR_NEO4J_PASSWORD
NEO4J_DATABASE=neo4j
```

`NEO4J_READ_ONLY=true` does not need to be placed in `.env`: System C forces
that value for the runtime MCP subprocess.

## 3. Existing Gemini config

Keep the frozen development model configuration:

```env
GEMINI_API_KEY=YOUR_KEY
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_THINKING_LEVEL=medium
```

## 4. Initialize the semantic graph

Neo4j must be running, then:

```powershell
python -m scripts.initialize_knowledge_graph
```

The seed script is idempotent (`MERGE` + `IF NOT EXISTS` constraints).

## 5. Preflight without using Gemini quota

```powershell
python -m scripts.check_system_c
```

This checks:
- imports;
- environment variables;
- Neo4j connectivity;
- semantic graph presence;
- System C import.

It does not call Gemini.

## 6. First System C development test

Start with the cohort-derived development task because it should use the KG:

```powershell
python -m scripts.run_system_c --task-id C4_DEV_01
```

Then test the difficult compositional task:

```powershell
python -m scripts.run_system_c --task-id C6_DEV_01
```

## 7. Evaluate

The existing common evaluator can read System C because the agent marks a
primary PostgreSQL result:

```powershell
python -m scripts.evaluate_results --system system_c
```

## Security design

Runtime Neo4j MCP:
- `NEO4J_READ_ONLY=true`;
- ADK exposes only `get-schema` and `read-cypher`;
- tool names are prefixed `kg_`.

PostgreSQL:
- SELECT/WITH only;
- one statement;
- allowlisted business tables only;
- read-only transaction;
- query timeout;
- row limit.

Agent:
- fixed tool/model budgets;
- per-task session only;
- tool output treated as untrusted data;
- no access to benchmark/gold or research truth;
- lightweight PII redaction;
- observable tool trajectory only (no private chain-of-thought logging).

## Held-out rule

Do not run:

```powershell
python -m scripts.run_system_c --split test --allow-test
```

until Systems A, B, and C are frozen.
