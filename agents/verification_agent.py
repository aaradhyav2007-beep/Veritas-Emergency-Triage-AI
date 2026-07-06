from skills.weather_geo_verify import weather_geo_verify
from skills.water_level_verify import water_level_verify
from skills.seismic_verify import seismic_verify
from skills.severity_score import detect_primary_hazard, score_from_text
from skills.ai_reasoning import assess_with_ai
from skills.corroboration import find_corroboration


def run_verification(incident: dict):
    image_path = incident.get("image_path")
    hazard = detect_primary_hazard(incident["report_text"])

    verification = weather_geo_verify(
        location=incident["location"],
        sensor_type=incident.get("sensor_type", ""),
        sensor_value=float(incident.get("sensor_value", 0)),
        hazard=hazard
    )

    # Water level verification for flood/tsunami claims
    if verification.get("location_verified") and verification.get("coordinates"):
        coords = verification["coordinates"]
        water_verification = water_level_verify(
            location=incident["location"],
            latitude=coords.get("latitude"),
            longitude=coords.get("longitude"),
            hazard=hazard
        )
        # Merge water level data into verification
        verification["water_level_risk_boost"] = water_verification.get("water_level_risk_boost", 0)
        verification["water_level_severity"] = water_verification.get("water_level_severity", "unknown")
        verification["live_water_data"] = water_verification.get("live_water_data")

    # Seismic activity verification for earthquake/landslide claims
    if verification.get("location_verified") and verification.get("coordinates"):
        coords = verification["coordinates"]
        seismic_verification = seismic_verify(
            location=incident["location"],
            latitude=coords.get("latitude"),
            longitude=coords.get("longitude"),
            hazard=hazard
        )
        # Merge seismic data into verification
        verification["seismic_risk_boost"] = seismic_verification.get("seismic_risk_boost", 0)
        verification["seismic_severity"] = seismic_verification.get("seismic_severity", "unknown")
        verification["live_seismic_data"] = seismic_verification.get("live_seismic_data")
        verification["closest_earthquake"] = seismic_verification.get("closest_earthquake")

    # AI reasoning pass (Gemini). Fails closed -- ai_available=False and
    # the rest of these keys stay at safe defaults if the call fails for
    # any reason (no key, network, bad response, etc).
    rule_score, keyword_hits = score_from_text(incident["report_text"])
    ai_assessment = assess_with_ai(
        incident=incident,
        verification=verification,
        hazard=hazard,
        image_path=image_path,
    )
    verification.update(ai_assessment)

    # Multi-report corroboration: check the audit log for independent
    # reports nearby/recently sharing a hazard with this one. Requires
    # verified coordinates -- skipped gracefully otherwise.
    coords = verification.get("coordinates") or {}
    corroboration = find_corroboration(
        current_lat=coords.get("latitude"),
        current_lon=coords.get("longitude"),
        current_hazards=keyword_hits,
    )
    verification["corroboration_count"] = corroboration["corroboration_count"]
    verification["corroboration_boost"] = corroboration["corroboration_boost"]
    verification["matches"] = corroboration["corroborating_reports"]

    return verification
