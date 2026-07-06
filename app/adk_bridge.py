"""
ADK Bridge
==========

Lets the Streamlit app run an incident through the actual Google ADK
agent (`adk/root_agent.py`) as an alternative to calling
`agents.orchestrator.process_incident` directly. When this path is used,
Gemini itself -- not our code -- decides whether to call the full
assessment tool, delegate to the verification sub-agent, or call the
MCP-exposed weather tool, based on the natural-language request built
from the incident form.

Lives outside `adk/` and `agents/` (not inside either) to avoid a
circular import: `adk/root_agent.py` already imports from `agents/`, so
`agents/` cannot import from `adk/` without a cycle. This module is the
one-way bridge from the UI layer into the agent layer.

Fails closed like the rest of this codebase: any failure (google-adk not
installed, the MCP subprocess not starting, a bad response, etc.) is
caught and returned as an error string, never raised into the Streamlit
UI.
"""

import asyncio


def _run_async(coro):
    """Run an async coroutine from Streamlit's synchronous callback context."""
    return asyncio.run(coro)


def _build_prompt(incident: dict) -> str:
    return (
        "Run a full emergency assessment on this citizen incident report. "
        f"Report text: \"{incident.get('report_text', '')}\". "
        f"Location: {incident.get('location', 'unknown')}. "
        f"Sensor type/value: {incident.get('sensor_type', 'none')} / "
        f"{incident.get('sensor_value', 'n/a')}. "
        f"Alert language: {incident.get('lang', 'en')}."
    )


async def _run_agent(incident: dict) -> dict:
    from google.genai import types
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from adk.root_agent import root_agent

    app_name = "veritas_streamlit"
    user_id = "streamlit_user"

    session_service = InMemorySessionService()
    session = await session_service.create_session(app_name=app_name, user_id=user_id)

    runner = Runner(app_name=app_name, agent=root_agent, session_service=session_service)

    content = types.Content(role="user", parts=[types.Part(text=_build_prompt(incident))])

    final_text = ""
    tool_calls = []
    transcript = []

    async for event in runner.run_async(
        user_id=user_id, session_id=session.id, new_message=content
    ):
        parts = getattr(getattr(event, "content", None), "parts", None) or []
        for part in parts:
            fn_call = getattr(part, "function_call", None)
            if fn_call is not None:
                name = getattr(fn_call, "name", "unknown_tool")
                tool_calls.append(name)
                transcript.append(f"[tool call] {name}")
            text = getattr(part, "text", None)
            if text:
                transcript.append(text)

        if hasattr(event, "is_final_response") and event.is_final_response():
            parts = getattr(getattr(event, "content", None), "parts", None) or []
            for part in parts:
                text = getattr(part, "text", None)
                if text:
                    final_text += text

    return {
        "final_text": final_text or "(Agent completed with no text response.)",
        "tool_calls": tool_calls,
        "transcript": "\n".join(transcript),
        "error": None,
    }


def run_incident_via_adk(incident: dict) -> dict:
    """
    Synchronous entry point for Streamlit. Returns:
        {"final_text": str, "tool_calls": [str, ...], "transcript": str, "error": None}
    or, on any failure:
        {"final_text": "", "tool_calls": [], "transcript": "", "error": "<reason>"}
    """
    try:
        return _run_async(_run_agent(incident))
    except Exception as e:
        return {
            "final_text": "",
            "tool_calls": [],
            "transcript": "",
            "error": f"{type(e).__name__}: {e}",
        }
