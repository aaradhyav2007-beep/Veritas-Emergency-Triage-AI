from agents.orchestrator import process_incident


def full_emergency_assessment(
    report_text: str,
    location: str,
    sensor_type: str = "",
    sensor_value: float = 0,
    lang: str = "en",
):
    """
    Run a complete emergency assessment: guardrails, verification,
    triage, and dispatch communication. Use this when the user wants
    a full incident assessment, not just a quick location/weather check.
    """
    incident = {
        "report_text": report_text,
        "location": location,
        "sensor_type": sensor_type,
        "sensor_value": sensor_value,
        "lang": lang,
    }
    return process_incident(incident)