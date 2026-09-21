"""Build the ADK root agent and Neo4j MCP toolset."""

from __future__ import annotations

import os
import sys

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools.mcp_tool import (
    McpToolset,
    StdioConnectionParams,
)
from google.genai import types
from mcp import StdioServerParameters

from .config import (
    APP_NAME,
    MODEL,
    NEO4J_DATABASE,
    NEO4J_PASSWORD,
    NEO4J_URI,
    NEO4J_USERNAME,
    THINKING_LEVEL,
)
from .plugins import ResearchGuardPlugin
from .prompt import AGENT_INSTRUCTION
from .tools import (
    calculate,
    create_visualization,
    query_database,
)


def build_agent():
    """
    Create System C with:
    - one bounded ADK root agent;
    - read-only Neo4j semantic access through MCP;
    - read-only PostgreSQL analytical access;
    - deterministic calculation and visualization tools.
    """

    # Start from the current process environment so Windows environment
    # variables required by the subprocess are preserved.
    mcp_env = dict(os.environ)

    # neo4j-mcp-server 1.6.0 uses the NEO4J_MCP_* variable names.
    # Values come from the same Neo4j configuration already validated
    # by the project's Python connectivity checks.
    mcp_env.update(
        {
            "NEO4J_MCP_URI": NEO4J_URI,
            "NEO4J_MCP_USERNAME": NEO4J_USERNAME,
            "NEO4J_MCP_PASSWORD": NEO4J_PASSWORD,
            "NEO4J_MCP_DATABASE": NEO4J_DATABASE,
            "NEO4J_MCP_READ_ONLY": "true",
            "NEO4J_MCP_TELEMETRY": "false",
            "NEO4J_MCP_LOG_LEVEL": "warning",
            "NEO4J_MCP_LOG_FORMAT": "text",
            "NEO4J_MCP_TRANSPORT_MODE": "stdio",
        }
    )

    knowledge_graph_toolset = McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                # Use the same Python interpreter/environment running System C.
                command=sys.executable,
                args=["-m", "neo4j_mcp_server"],
                env=mcp_env,
            ),
            timeout=30.0,
        ),

        # Defense in depth:
        # 1. Neo4j MCP itself is configured read-only.
        # 2. ADK exposes only the two semantic-read tools required by System C.
        tool_filter=[
            "get-schema",
            "read-cypher",
        ],
        tool_name_prefix="kg_",
        use_mcp_resources=False,
    )

    model = Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(
            attempts=2,
            initial_delay=1.0,
            max_delay=8.0,
            exp_base=2.0,
            jitter=0.2,
        ),
    )

    root_agent = Agent(
        name="dealer_analytics_agent",
        description=(
            "Tool-grounded dealer analytics agent using PostgreSQL, "
            "deterministic analytic tools, and a Neo4j semantic "
            "knowledge graph."
        ),
        model=model,
        instruction=AGENT_INSTRUCTION,
        tools=[
            knowledge_graph_toolset,
            query_database,
            calculate,
            create_visualization,
        ],
        generate_content_config=types.GenerateContentConfig(
            temperature=0.0,
            thinking_config=types.ThinkingConfig(
                thinking_level=THINKING_LEVEL,
                include_thoughts=False,
            ),
        ),
        mode="task",
    )

    app = App(
        name=APP_NAME,
        root_agent=root_agent,
        plugins=[ResearchGuardPlugin()],
    )

    return root_agent, app, knowledge_graph_toolset