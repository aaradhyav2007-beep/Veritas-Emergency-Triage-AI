import sys
from google.adk.agents import Agent
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

from .verification_agent import verification_agent
from .incident_tool import full_emergency_assessment

weather_mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable,
            args=["mcp_server/server.py"],
        ),
        timeout=10,
    ),
)

root_agent = Agent(
    name="veritas",
    model="gemini-3.5-flash",
    description="Root agent for the Veritas Emergency Decision Support System.",
    instruction="""
You are Veritas, an AI-powered Emergency Decision Support System.

You have three capabilities:
1. Verification only — use the Verification Agent for a full verification summary.
2. Full assessment — use full_emergency_assessment for complete triage, severity, and dispatch.
3. Quick MCP weather check — use verify_location_weather (an MCP tool) when the user
   specifically wants a fast standalone weather/location check via the MCP server.

Rules:
- Never invent weather, verification, or severity results yourself.
- Always rely on tool/sub-agent output, never guess.
- Default to a full assessment if unsure.
""",
    sub_agents=[verification_agent],
    tools=[full_emergency_assessment, weather_mcp_toolset],
)