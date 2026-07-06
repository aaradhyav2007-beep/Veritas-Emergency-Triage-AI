from google.adk.agents import Agent

from agents.verification_agent import run_verification


def verify_incident(
    location: str,
    report_text: str = "",
    sensor_type: str = "",
    sensor_value: float = 0,
):
    """
    Verify an emergency incident using location, weather,
    and sensor information.

    Returns verified incident information.
    """

    incident = {
        "report_text": report_text,
        "location": location,
        "sensor_type": sensor_type,
        "sensor_value": sensor_value,
    }

    return run_verification(incident)


verification_agent = Agent(
    name="verification_agent",
    model='gemini-2.5-flash',
    description="Verifies emergency incidents.",
    instruction="""
    You are the Verification Agent for Veritas.

    Your responsibilities:
    1. Always use the verify_incident tool for verification.
    2. Never invent weather, location, or sensor information.
    3. Base your response only on the tool output.
    4. After receiving the tool output, summarize the findings in clear professional language.

    Your summary should include:
    - Incident location
    - Whether the location was successfully verified
    - Current weather conditions (if available)
    - Sensor information (if provided)
    - Key evidence sources used
    - Any limitations or missing information

    Do not output raw Python dictionaries unless explicitly requested.
    """,
    tools=[verify_incident],
)