"""
Corroboration Skill

Scans the audit log (data/incidents.jsonl) for independent prior reports
that share a detected hazard with the current incident and are both
geographically close and recent. Multiple independent reports of the same
hazard are treated as evidence that boosts triage confidence and severity.

This module never raises: a missing/unreadable audit log, malformed
lines, or missing coordinates simply mean zero corroboration found.
"""

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

AUDIT_PATH = Path("data/incidents.jsonl")

# A prior report counts as corroboration if it's within this radius...
MAX_DISTANCE_KM = 5.0
# ...and was filed within this time window.
MAX_AGE = timedelta(hours=6)

# Points added to the triage score per corroborating report, capped.
BOOST_PER_MATCH = 10
MAX_BOOST = 20


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _parse_timestamp(ts: str):
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        return None


def find_corroboration(current_lat, current_lon, current_hazards):
    """
    current_lat / current_lon: verified coordinates of the current
        incident, or None if location verification failed.
    current_hazards: list of hazard keyword-hits for the current report
        (from skills.severity_score.score_from_text).

    Returns a dict with corroboration_count, corroboration_boost, and
    corroborating_reports (list of {location, distance_km, report_text}).
    """
    empty = {
        "corroboration_count": 0,
        "corroboration_boost": 0,
        "corroborating_reports": [],
    }

    if current_lat is None or current_lon is None or not current_hazards:
        return empty

    if not AUDIT_PATH.exists():
        return empty

    now = datetime.now(timezone.utc)
    current_hazard_set = set(current_hazards)
    matches = []

    try:
        with open(AUDIT_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return empty

    for line in lines:
        line = line.strip()
        if not line:
            continue

        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        # Only consider completed incident-processing entries, not
        # human-review-action log lines.
        if entry.get("type") == "human_review_action":
            continue

        result = entry.get("result") or {}
        if result.get("status") == "blocked":
            continue

        ts = _parse_timestamp(entry.get("timestamp", ""))
        if ts is None or (now - ts) > MAX_AGE:
            continue

        verification = result.get("verification") or {}
        coords = verification.get("coordinates") or {}
        lat, lon = coords.get("latitude"), coords.get("longitude")
        if lat is None or lon is None:
            continue

        distance = _haversine_km(current_lat, current_lon, lat, lon)
        if distance > MAX_DISTANCE_KM:
            continue

        prior_hazards = set((result.get("triage") or {}).get("keyword_hits", []))
        if not (prior_hazards & current_hazard_set):
            continue

        incident_info = entry.get("incident") or {}
        matches.append({
            "location": incident_info.get("location", "Unknown"),
            "distance_km": round(distance, 2),
            "report_text": incident_info.get("report_text", ""),
        })

    count = len(matches)
    boost = min(MAX_BOOST, count * BOOST_PER_MATCH)

    return {
        "corroboration_count": count,
        "corroboration_boost": boost,
        "corroborating_reports": matches,
    }