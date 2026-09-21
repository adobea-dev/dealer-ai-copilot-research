from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> None:
    load_dotenv()

    required = [
        "NEO4J_MCP_URI",
        "NEO4J_MCP_USERNAME",
        "NEO4J_MCP_PASSWORD",
    ]

    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError(
            "Missing MCP environment variables: "
            + ", ".join(missing)
        )

    # Preserve the complete Windows environment and pass the
    # variables loaded from .env to the MCP subprocess.
    child_env = dict(os.environ)

    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "neo4j_mcp_server"],
        env=child_env,
    )

    print("=" * 70)
    print("NEO4J MCP DIRECT HANDSHAKE TEST")
    print("=" * 70)
    print(f"Python:   {sys.executable}")
    print(f"URI:      {os.getenv('NEO4J_MCP_URI')}")
    print(f"Database: {os.getenv('NEO4J_MCP_DATABASE', 'neo4j')}")
    print("Password: [hidden]")
    print()

    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:

            print("[1] Initializing MCP session...")
            await session.initialize()
            print("[PASS] MCP session initialized.")

            print("\n[2] Listing tools...")
            tools_result = await session.list_tools()

            tool_names = [tool.name for tool in tools_result.tools]

            for name in tool_names:
                print(f"  - {name}")

            print("\n[3] Testing read-only Cypher...")

            # Find the Cypher read tool. Versions may use slightly
            # different tool naming conventions.
            read_tool = None

            for candidate in (
                "read-cypher",
                "read_cypher",
                "read-query",
                "read_query",
            ):
                if candidate in tool_names:
                    read_tool = candidate
                    break

            if read_tool is None:
                print(
                    "[INFO] MCP connected successfully, but no expected "
                    "read-Cypher tool name was found."
                )
                print("Available tools:", tool_names)
            else:
                result = await session.call_tool(
                    read_tool,
                    {
                        "query": (
                            "MATCH (n) "
                            "RETURN count(n) AS node_count"
                        )
                    },
                )

                print(f"[PASS] {read_tool} executed.")
                print(result)

    print()
    print("=" * 70)
    print("[PASS] NEO4J MCP TEST COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())