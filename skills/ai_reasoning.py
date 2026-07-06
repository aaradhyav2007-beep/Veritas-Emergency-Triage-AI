"""
AI Reasoning Skill
==================

Calls Gemini (via google-genai) to provide a second, independent
assessment of an incident report, on top of the rule-based keyword
scorer and the environmental verification passes (weather, water level,
seismic activity).

This module fails CLOSED: if GOOGLE_API_KEY is missing, the API call
errors, or the response can't be parsed, assess_with_ai returns
ai_available=False and safe defaults rather than raising.
"""

import json
import logging
import os

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

MODEL_NAME = "gemini-3.5-flash"

_SAFE_DEFAULTS = {
    "ai_score": None,
    "ai_available": False,
    "ai_confidence": 0.0,
    "negated": False,
    "contradicts_evidence": False,
    "rationale": "",
    "ai_error": None,
}


def _build_prompt(incident: dict, verification: dict, hazard: str) -> str:
    weather = verification.get("live_weather") or {}
    water_data = verification.get("live_water_data") or {}
    seismic_data = verification.get("live_seismic_data") or {}
    closest_eq = verification.get("closest_earthquake") or {}
    
    # Format water level info
    water_info = "No significant river discharge detected (API checked, no active floods)"
    if water_data and water_data.get("current_discharge_m3s", 0) > 0:
        water_info = f"discharge={water_data.get('current_discharge_m3s', 'n/a')}m3/s ({verification.get('water_level_severity', 'normal')})"
    
    # Format seismic info
    seismic_info = "No recent significant seismic activity detected (USGS checked, clear)"
    if closest_eq:
        seismic_info = f"closest event: M{closest_eq.get('magnitude', 'n/a')} at {closest_eq.get('distance_km', 'n/a')}km ({closest_eq.get('hours_ago', 'n/a')}h ago)"

    return f"""You are an emergency triage reasoning assistant. Assess the
following citizen incident report using ONLY the information given below.
Do not invent facts.

Report text: "{incident.get('report_text', '')}"
Stated location: {incident.get('location', 'unknown')}
Primary keyword-detected hazard: {hazard or 'none detected'}

--- SENSOR DATA (Manual entry from citizen/field device) ---
Sensor type: {incident.get('sensor_type', 'none')}
Sensor value: {incident.get('sensor_value', 'n/a')} (0-100 scale)

--- EXTERNAL VERIFICATION DATA (Live API feeds) ---
Location verified: {verification.get('location_verified', False)}
Live weather: temp={weather.get('temperature_2m', 'n/a')}C, precip={weather.get('precipitation', 'n/a')}mm, wind={weather.get('wind_speed_10m', 'n/a')}km/h
Water level: {water_info}
Seismic activity: {seismic_info}

Respond with ONLY a JSON object (no markdown fences, no extra text) with
exactly these fields:
{{
  "score": <integer 0-100, your independent severity estimate>,
  "confidence": <float 0.0-1.0, how confident you are in this assessment>,
  "negated": <true if the report explicitly retracts/negates the hazard, else false>,
  "contradicts_evidence": <true if the report's claims conflict with the EXTERNAL VERIFICATION DATA above, else false>,
  "rationale": <one short sentence explaining your assessment, clearly distinguishing between sensor readings and external API data>
}}"""


def assess_with_ai(incident: dict, verification: dict, hazard: str = None, image_path: str = None) -> dict:
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        defaults = dict(_SAFE_DEFAULTS)
        defaults["ai_error"] = "GOOGLE_API_KEY not set"
        return defaults

    try:
        client = genai.Client(api_key=api_key)
        prompt = _build_prompt(incident, verification, hazard)
        
        contents = [prompt]
        if image_path and os.path.exists(image_path):
            try:
                with open(image_path, "rb") as f:
                    image_data = f.read()
                # Determine mime type from extension
                mime_type = "image/jpeg"
                if image_path.lower().endswith(".png"):
                    mime_type = "image/png"
                elif image_path.lower().endswith(".webp"):
                    mime_type = "image/webp"
                
                contents.append(
                    types.Part.from_bytes(data=image_data, mime_type=mime_type)
                )
                # NOTE: `prompt` was already placed in `contents` above, so
                # mutating the `prompt` string here would NOT reach the
                # model -- append the extra instruction as its own part.
                contents.append(
                    "An image has been attached to this report. Use it as "
                    "primary evidence to verify the claims. Does the image "
                    "show the hazard? Does it look like a real photo or a "
                    "generated/fake one?"
                )
            except Exception as img_err:
                logger.warning(f"Failed to load image for AI reasoning: {img_err}")

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
        )

        text = (response.text or "").strip()
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

        data = json.loads(text)

        score = data.get("score")
        score = max(0, min(100, int(score))) if score is not None else None

        confidence = data.get("confidence", 0.0)
        confidence = max(0.0, min(1.0, float(confidence)))

        return {
            "ai_score": score,
            "ai_available": True,
            "ai_confidence": confidence,
            "negated": bool(data.get("negated", False)),
            "contradicts_evidence": bool(data.get("contradicts_evidence", False)),
            "rationale": str(data.get("rationale", "")),
            "ai_error": None,
        }

    except Exception as e:
        logger.warning("AI reasoning call failed: %s: %s", type(e).__name__, e)
        defaults = dict(_SAFE_DEFAULTS)
        defaults["ai_error"] = f"{type(e).__name__}: {e}"
        return defaults
