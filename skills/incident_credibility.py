from typing import Dict


def assess_incident_credibility(
    report: str,
    verification: Dict,
    detected_hazards: list,
):
    """
    Assess how credible an incident report appears based on
    available evidence.

    This does NOT determine whether a report is fake.
    It evaluates how well the available evidence supports
    the reported incident.
    """

    score = 0
    reasons = []

    # -------------------------
    # Location Verification
    # -------------------------
    if verification.get("location_verified"):
        score += 40
        reasons.append("Verified location.")
    else:
        reasons.append("Location could not be verified.")

    # -------------------------
    # Hazard Detection
    # -------------------------
    if detected_hazards:
        score += 30
        reasons.append(
            f"Hazard identified: {', '.join(detected_hazards)}."
        )
    else:
        reasons.append("No recognizable hazard detected.")

    # -------------------------
    # Environmental Data Availability
    # -------------------------
    # Weather data
    weather = verification.get("live_weather")
    water_data = verification.get("live_water_data")
    seismic_data = verification.get("live_seismic_data")

    environmental_score = 0
    environmental_sources = []

    if weather:
        environmental_score += 10
        environmental_sources.append("weather")

    if water_data:
        environmental_score += 10
        environmental_sources.append("water level")

    if seismic_data:
        environmental_score += 10
        environmental_sources.append("seismic activity")

    score += environmental_score

    if environmental_sources:
        reasons.append(f"Live data available: {', '.join(environmental_sources)}.")
    else:
        reasons.append("No live environmental data available.")

    # -------------------------
    # Report Completeness
    # -------------------------
    if len(report.split()) >= 8:
        score += 10
        reasons.append("Report contains useful details.")
    else:
        reasons.append("Report contains limited details.")

    # -------------------------
    # Final Rating
    # -------------------------
    if score >= 90:
        credibility = "High"
    elif score >= 50:
        credibility = "Medium"
    else:
        credibility = "Low"

    return {
        "credibility": credibility,
        "score": score,
        "reasons": reasons,
    }
