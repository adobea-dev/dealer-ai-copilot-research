# Semantic Knowledge Graph

The Neo4j graph is deliberately a semantic layer, not a copy of the
transactional PostgreSQL database.

It contains:
- funnel-stage semantics;
- metric definitions and formulas;
- event-period/cohort semantics;
- dimensions;
- country code mappings;
- physical schema mappings;
- relational linkage semantics.

It does **not** contain:
- dealer performance outcomes;
- benchmark answers;
- gold SQL;
- hidden simulation truth;
- latent quality parameters.

PostgreSQL remains the sole authoritative source of research facts.
