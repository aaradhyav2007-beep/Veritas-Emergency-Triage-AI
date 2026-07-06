"""
Evidence Engine
================

Builds a single, auditable evidence profile for a triaged incident by
combining every independent signal the pipeline collected: geocoded
location verification, live weather/sensor readings, water level data,
seismic activity, the independent Gemini reasoning pass, multi-report
corroboration from the audit log, and citizen report credibility.

This module deliberately does NOT re-score the incident -- that math
belongs to `agents/triage_agent.py`. Its job is to explain *why* the
triage numbers came out the way they did, count how many independent
sources actually agree with the report, flag contradictions, turn all
of that into an explicit fake-vs-real verdict ("Likely Real" /
"Likely Fake" / "Disputed -- Needs Human Review" / "Unverified" /
"Resolved / False Alarm"), and turn all of that into a recommendation
a human dispatcher can act on without reading raw JSON.

The verdict is deliberately conservative: a single credible
contradiction can only produce "Likely Fake" when almost nothing else
backs the report. If real evidence is still supporting it, the report
is "Disputed" and routed to a human instead of auto-labeled -- this
system flags suspicious reports for review, it does not silently
discard them.

Fails soft: a missing or partial `verification`/`triage` dict is
treated as "this evidence source is unavailable", never raises, and
never gets silently treated as if the source agreed with the report.
"""

from __future__ import annotations

from typing import Optional

from skills.incident_credibility import assess_incident_credibility

# Minimum number of independent sources actively *supporting* the report
# required to reach each evidence-strength tier. Any contradiction caps
# the tier at "Weak" regardless of how many sources otherwise agree --
# a single credible contradiction (e.g. AI reasoning flags the report as
# a false alarm) should not be outvoted by quantity.
_STRONG_MIN_SUPPORTING = 4
_MODERATE_MIN_SUPPORTING = 2

_STATUS_ICON = {
    "supports": "✅",
    "contradicts": "⚠️",
    "unavailable": "➖",
    "neutral": "ℹ️",
}

# ---------------------------------------------------------------------
# Individual evidence sources
#
# Each `_*_source` function inspects one independent signal and returns
# {"name", "status", "detail"} where status is one of:
#   "supports"    -- this source actively backs the reported hazard
#   "contradicts" -- this source conflicts with the reported hazard
#   "neutral"     -- this source ran successfully but is inconclusive
#   "unavailable" -- this source didn't produce usable evidence at all
# ---------------------------------------------------------------------

def _location_source(verification: dict) -> dict:
    if verification.get("location_verified"):
        return {
            "name": "Location",
            "status": "supports",
            "detail": "Reported location was verified against a live geocoder.",
        }
    return {
        "name": "Location",
        "status": "unavailable",
        "detail": "Location could not be verified.",
    }


def _weather_source(verification: dict) -> dict:
    weather = verification.get("live_weather")
    boost = verification.get("weather_risk_boost", 0) or 0

    if not weather:
        return {
            "name": "Weather / sensor",
            "status": "neutral",
            "detail": "Live weather data checked; conditions are within normal range.",
        }
    if boost > 0:
        return {
            "name": "Weather / sensor",
            "status": "supports",
            "detail": f"Live weather/sensor conditions raised risk (+{boost}).",
        }
    return {
        "name": "Weather / sensor",
        "status": "neutral",
        "detail": "Live weather retrieved but conditions were unremarkable.",
    }


def _water_level_source(verification: dict) -> dict:
    """Evaluate water level / flood risk from live river discharge data."""
    water_data = verification.get("live_water_data")
    boost = verification.get("water_level_risk_boost", 0) or 0
    severity = verification.get("water_level_severity", "unknown")

    if not water_data:
        return {
            "name": "Water level",
            "status": "unavailable",
            "detail": "Live water level data unavailable.",
        }
    
    if boost > 0:
        current_discharge = water_data.get("current_discharge_m3s", "?")
        return {
            "name": "Water level",
            "status": "supports",
            "detail": f"Elevated river discharge ({current_discharge} m³/s, {severity}) raised flood risk (+{boost}).",
        }
    
    return {
        "name": "Water level",
        "status": "neutral",
        "detail": "Live water levels checked; discharge is within normal safety range.",
    }


def _seismic_source(verification: dict) -> dict:
    """Evaluate seismic activity / earthquake risk from recent seismic events."""
    seismic_data = verification.get("live_seismic_data")
    boost = verification.get("seismic_risk_boost", 0) or 0
    severity = verification.get("seismic_severity", "unknown")
    closest_eq = verification.get("closest_earthquake")

    if not seismic_data:
        return {
            "name": "Seismic activity",
            "status": "unavailable",
            "detail": "Seismic data unavailable.",
        }
    
    if boost > 0 and closest_eq:
        magnitude = closest_eq.get("magnitude", "?")
        distance = closest_eq.get("distance_km", "?")
        hours_ago = closest_eq.get("hours_ago", "?")
        return {
            "name": "Seismic activity",
            "status": "supports",
            "detail": f"Recent seismic activity (M{magnitude} {distance}km away, {hours_ago:.1f}h ago, {severity}) raised earthquake/landslide risk (+{boost}).",
        }
    
    return {
        "name": "Seismic activity",
        "status": "neutral",
        "detail": "Live seismic activity checked; no significant recent events detected.",
    }


def _ai_reasoning_source(verification: dict) -> dict:
    if not verification.get("ai_available"):
        error = verification.get("ai_error")
        detail = (
            f"Independent AI reasoning pass did not run ({error})."
            if error
            else "Independent AI reasoning pass did not run (no key or call failed)."
        )
        return {
            "name": "AI reasoning",
            "status": "unavailable",
            "detail": detail,
        }

    rationale = verification.get("rationale") or ""

    if verification.get("negated"):
        return {
            "name": "AI reasoning",
            "status": "contradicts",
            "detail": rationale or "AI reasoning found the report negates/retracts the hazard.",
        }
    if verification.get("contradicts_evidence"):
        return {
            "name": "AI reasoning",
            "status": "contradicts",
            "detail": rationale or "AI reasoning conflicts with the collected evidence.",
        }
    return {
        "name": "AI reasoning",
        "status": "supports",
        "detail": rationale or "AI reasoning is consistent with the reported hazard.",
    }


def _corroboration_source(verification: dict) -> dict:
    count = verification.get("corroboration_count", 0) or 0
    if count > 0:
        return {
            "name": "Corroboration",
            "status": "supports",
            "detail": f"{count} independent nearby report(s) share this hazard.",
        }
    return {
        "name": "Corroboration",
        "status": "neutral",
        "detail": "No independent corroborating reports found nearby/recently.",
    }


def _credibility_source(credibility: dict) -> dict:
    label = credibility.get("credibility", "Low")
    if label == "High":
        return {
            "name": "Report credibility",
            "status": "supports",
            "detail": "Citizen report is detailed and well-supported by available evidence.",
        }
    if label == "Medium":
        return {
            "name": "Report credibility",
            "status": "neutral",
            "detail": "Citizen report contains moderate supporting detail.",
        }
    return {
        "name": "Report credibility",
        "status": "neutral",
        "detail": "Citizen report lacks sufficient supporting detail.",
    }


def gather_sources(verification: dict, credibility: dict) -> list:
    """Evaluate every independent evidence source for this incident."""
    return [
        _location_source(verification),
        _weather_source(verification),
        _water_level_source(verification),
        _seismic_source(verification),
        _ai_reasoning_source(verification),
        _corroboration_source(verification),
        _credibility_source(credibility),
    ]


# ---------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------

def _reasons_and_warnings(sources: list, hazards: list) -> tuple:
    reasons, warnings = [], []

    if hazards:
        reasons.append(
            f"Hazard keyword(s) detected: {', '.join(h.title() for h in hazards)}."
        )
    else:
        warnings.append("No recognizable hazard keywords detected in the report text.")

    for source in sources:
        if source["status"] == "supports":
            reasons.append(source["detail"])
        elif source["status"] == "contradicts":
            warnings.append(source["detail"])
        elif source["status"] == "unavailable":
            warnings.append(source["detail"])
        # "neutral" sources are successful checks that didn't find active evidence.
        # We don't add them to reasons/warnings to keep the UI clean,
        # but they will show up in the "Evidence Sources" list with an 'info' icon.

    return reasons, warnings


def _evidence_strength(sources: list) -> str:
    supporting = sum(1 for s in sources if s["status"] == "supports")
    contradicted = any(s["status"] == "contradicts" for s in sources)

    if contradicted:
        return "Weak"
    if supporting >= _STRONG_MIN_SUPPORTING:
        return "Strong"
    if supporting >= _MODERATE_MIN_SUPPORTING:
        return "Moderate"
    if supporting >= 1:
        return "Weak"
    return "Insufficient"


def _verdict(evidence_strength: str, sources: list, triage: dict) -> tuple:
    """
    The explicit fake-vs-real call.

    `evidence_strength` measures how much support exists; it doesn't by
    itself say whether a report is fabricated. `_verdict` folds in *why*
    the strength came out the way it did -- specifically, whether the
    weakness is "nobody has weighed in yet" (Unverified) or "something
    active contradicts this report" (Likely Fake) -- so a dispatcher gets
    a single, decisive answer instead of a strength number to interpret
    themselves.

    Returns (verdict, verdict_reason).
    """
    contradicting = [s for s in sources if s["status"] == "contradicts"]
    supporting = sum(1 for s in sources if s["status"] == "supports")

    if triage.get("ai_negated"):
        return (
            "Resolved / False Alarm",
            "The report itself indicates the hazard was retracted or resolved.",
        )

    if contradicting:
        names = ", ".join(s["name"] for s in contradicting)
        if supporting >= _MODERATE_MIN_SUPPORTING:
            return (
                "Disputed -- Needs Human Review",
                f"{names} contradict(s) the report, but {supporting} other "
                f"independent source(s) still support it. Signals conflict; "
                f"do not auto-label as fake or real.",
            )
        return (
            "Likely Fake",
            f"{names} actively contradict(s) the report, and only "
            f"{supporting} independent source(s) support it.",
        )

    if evidence_strength in ("Strong", "Moderate"):
        return (
            "Likely Real",
            f"{supporting} independent source(s) corroborate the report "
            f"and none contradict it.",
        )

    if evidence_strength == "Weak":
        supporting = sum(1 for s in sources if s["status"] == "supports")
        if supporting >= 1:
            return (
                "Unverified",
                "One independent source supports the report, but that's not "
                "enough corroboration to call it real yet.",
            )
        else:
            return (
                "Unverified",
                "External APIs checked but found no active evidence to confirm or contradict this report.",
            )

    return (
        "Unverified",
        "No independent source has confirmed or contradicted this report yet.",
    )


def _recommendation(triage: dict, evidence_strength: str) -> str:
    if triage.get("ai_negated"):
        return "No action needed -- report indicates the hazard was resolved or a false alarm."
    if triage.get("ai_contradicts_evidence"):
        return "Route to a human reviewer -- AI reasoning conflicts with verified evidence."

    tier = triage.get("tier", "Low")

    if evidence_strength == "Strong" and tier in ("High", "Critical"):
        return "Dispatch immediately."
    if evidence_strength in ("Strong", "Moderate"):
        return "Dispatch with standard monitoring." if tier != "Low" else "Log and monitor -- low severity."
    if evidence_strength == "Weak":
        return "Request human verification before dispatch."
    return "Hold -- insufficient evidence to act; request more information."


def _explanation(
    triage: dict, evidence_strength: str, recommendation: str, sources: list, verdict: str
) -> str:
    supporting_names = [s["name"] for s in sources if s["status"] == "supports"]
    tier = triage.get("tier", "Unknown")
    score = triage.get("final_score", 0)

    if supporting_names:
        support_txt = (
            f"{len(supporting_names)} independent source(s) "
            f"({', '.join(supporting_names)}) support the report."
        )
    else:
        support_txt = "No independent source currently supports the report."

    return (
        f"Verdict: {verdict}. Severity assessed as {tier} ({score}/100) with "
        f"{evidence_strength.lower()} evidence. {support_txt} "
        f"Recommendation: {recommendation}"
    )


def analyze_evidence(verification: dict, triage: dict, credibility: dict) -> tuple:
    """
    Evaluate all collected evidence and return (reasons, warnings, sources)
    for the given incident's verification/triage/credibility results.
    """
    hazards = triage.get("keyword_hits", []) or []
    sources = gather_sources(verification, credibility)
    reasons, warnings = _reasons_and_warnings(sources, hazards)
    return reasons, warnings, sources


def build_evidence(
    incident: dict,
    verification: dict,
    triage: dict,
    credibility: Optional[dict] = None,
) -> dict:
    """
    Combine every verification signal the pipeline collected into a
    single, explainable evidence profile.

    Parameters
    ----------
    incident:
        The raw incident dict (report_text, location, sensor_type, ...).
    verification:
        Output of `agents.verification_agent.run_verification` (weather/
        geo, water level, seismic, AI reasoning, corroboration all folded in).
    triage:
        Output of `agents.triage_agent.run_triage` (final_score, tier,
        confidence, keyword_hits, negation/contradiction flags, ...).
    credibility:
        Optional pre-computed output of
        `skills.incident_credibility.assess_incident_credibility`. If not
        supplied, it's computed here from the incident/verification/
        triage data so callers can pass just the three pipeline dicts.

    Returns
    -------
    dict with `location`, `incident_type`, `sources`, `credibility`,
    `reasons`, `warnings`, and a final `assessment` (evidence_strength,
    confidence, recommendation, explanation).
    """
    incident = incident or {}
    verification = verification or {}
    triage = triage or {}
    hazards = triage.get("keyword_hits", []) or []

    if credibility is None:
        credibility = assess_incident_credibility(
            report=incident.get("report_text", ""),
            verification=verification,
            detected_hazards=hazards,
        )

    reasons, warnings, sources = analyze_evidence(verification, triage, credibility)
    evidence_strength = _evidence_strength(sources)
    verdict, verdict_reason = _verdict(evidence_strength, sources, triage)
    recommendation = _recommendation(triage, evidence_strength)
    explanation = _explanation(triage, evidence_strength, recommendation, sources, verdict)

    return {
        "location": incident.get("location"),
        "incident_type": hazards[0] if hazards else None,
        "sources": sources,
        "credibility": credibility,
        "reasons": reasons,
        "warnings": warnings,
        "assessment": {
            "verdict": verdict,
            "verdict_reason": verdict_reason,
            "evidence_strength": evidence_strength,
            "confidence": triage.get("confidence", 0.0),
            "recommendation": recommendation,
            "explanation": explanation,
        },
    }


def describe_sources(sources: list) -> str:
    """Human-readable, icon-prefixed summary of every evidence source."""
    if not sources:
        return "No evidence sources evaluated."
    return "\n".join(
        f"{_STATUS_ICON.get(s['status'], '•')} {s['name']}: {s['detail']}"
        for s in sources
    )
