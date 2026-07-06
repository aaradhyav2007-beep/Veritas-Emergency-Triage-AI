"""
Tests for skills/evidence_engine.py.

These call `build_evidence` directly with hand-built `verification` /
`triage` dicts (the same shapes `run_verification` / `run_triage`
produce), so no network calls are made.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skills.evidence_engine import build_evidence, analyze_evidence, gather_sources


INCIDENT = {
    "report_text": "There is heavy smoke and possible forest fire near Central School.",
    "location": "Central School, Sector 7",
    "sensor_type": "smoke",
    "sensor_value": 72.0,
}


def full_verification(**overrides):
    """A fully-populated, 'everything succeeded and agrees' verification dict."""
    v = {
        "location_verified": True,
        "weather_risk_boost": 20,
        "live_weather": {"temperature_2m": 30, "precipitation": 8, "wind_speed_10m": 45},
        "ai_available": True,
        "ai_score": 85,
        "ai_confidence": 0.9,
        "negated": False,
        "contradicts_evidence": False,
        "rationale": "Report is consistent with detected smoke/fire hazard.",
        "corroboration_count": 2,
        "corroboration_boost": 16,
        "matches": [{"location": "Nearby St", "distance_km": 1.1, "report_text": "Saw fire too"}],
    }
    v.update(overrides)
    return v


def full_triage(**overrides):
    t = {
        "rule_score": 55,
        "ai_score": 85,
        "final_score": 78,
        "tier": "High",
        "confidence": 0.9,
        "keyword_hits": ["fire", "smoke"],
        "resources": ["Fire brigade", "Ambulance", "Police unit"],
        "ai_available": True,
        "ai_rationale": "Consistent with reported hazard.",
        "ai_negated": False,
        "ai_contradicts_evidence": False,
        "corroboration_count": 2,
        "corroboration_matches": [{"location": "Nearby St", "distance_km": 1.1, "report_text": "Saw fire too"}],
    }
    t.update(overrides)
    return t


# ---------------------------------------------------------------------
# build_evidence: output contract
# ---------------------------------------------------------------------

def test_build_evidence_has_expected_top_level_keys():
    result = build_evidence(INCIDENT, full_verification(), full_triage())
    expected_keys = {"location", "incident_type", "sources", "credibility", "reasons", "warnings", "assessment"}
    assert expected_keys.issubset(result.keys())


def test_build_evidence_assessment_has_expected_keys():
    result = build_evidence(INCIDENT, full_verification(), full_triage())
    assessment_keys = {"evidence_strength", "confidence", "recommendation", "explanation"}
    assert assessment_keys.issubset(result["assessment"].keys())


def test_location_and_incident_type_carried_through():
    result = build_evidence(INCIDENT, full_verification(), full_triage())
    assert result["location"] == INCIDENT["location"]
    assert result["incident_type"] == "fire"


def test_does_not_raise_on_missing_verification_or_triage():
    result = build_evidence(INCIDENT, {}, {})
    assert result["assessment"]["evidence_strength"] == "Insufficient"


def test_does_not_raise_on_none_inputs():
    result = build_evidence(INCIDENT, None, None)
    assert isinstance(result["reasons"], list)
    assert isinstance(result["warnings"], list)


# ---------------------------------------------------------------------
# Evidence strength tiers
# ---------------------------------------------------------------------

def test_all_sources_agreeing_yields_strong_evidence():
    result = build_evidence(INCIDENT, full_verification(), full_triage())
    assert result["assessment"]["evidence_strength"] in ("Strong", "Moderate")


def test_no_supporting_sources_yields_insufficient():
    bare_verification = {"location_verified": False}
    bare_triage = {"keyword_hits": [], "tier": "Low", "confidence": 0.1}
    result = build_evidence(
        {"report_text": "quiet", "location": "nowhere"}, bare_verification, bare_triage
    )
    assert result["assessment"]["evidence_strength"] == "Insufficient"


def test_contradiction_caps_strength_at_weak_even_with_many_supporters():
    verification = full_verification(contradicts_evidence=True)
    triage = full_triage(ai_contradicts_evidence=True)
    result = build_evidence(INCIDENT, verification, triage)
    assert result["assessment"]["evidence_strength"] == "Weak"


def test_negated_report_is_treated_as_contradiction():
    verification = full_verification(negated=True)
    triage = full_triage(ai_negated=True, final_score=15, tier="Low")
    result = build_evidence(INCIDENT, verification, triage)
    assert result["assessment"]["evidence_strength"] == "Weak"
    assert "false alarm" in result["assessment"]["recommendation"].lower() \
        or "resolved" in result["assessment"]["recommendation"].lower()


def test_more_supporting_sources_never_yields_weaker_tier():
    """Monotonicity: adding a second supporting source (corroboration)
    should never make the evidence look weaker."""
    weaker = build_evidence(
        INCIDENT,
        full_verification(corroboration_count=0),
        full_triage(corroboration_count=0),
    )
    stronger = build_evidence(
        INCIDENT,
        full_verification(corroboration_count=3),
        full_triage(corroboration_count=3),
    )
    order = {"Insufficient": 0, "Weak": 1, "Moderate": 2, "Strong": 3}
    assert order[stronger["assessment"]["evidence_strength"]] >= order[weaker["assessment"]["evidence_strength"]]


# ---------------------------------------------------------------------
# Fake / real verdict
# ---------------------------------------------------------------------

def test_assessment_includes_verdict_and_reason():
    result = build_evidence(INCIDENT, full_verification(), full_triage())
    assert "verdict" in result["assessment"]
    assert "verdict_reason" in result["assessment"]


def test_all_sources_agreeing_yields_likely_real():
    result = build_evidence(INCIDENT, full_verification(), full_triage())
    assert result["assessment"]["verdict"] == "Likely Real"


def test_contradiction_with_little_support_yields_likely_fake():
    verification = full_verification(
        location_verified=False,
        live_weather=None,
        weather_risk_boost=0,
        contradicts_evidence=True,
        corroboration_count=0,
        matches=[],
    )
    triage = full_triage(
        ai_contradicts_evidence=True, corroboration_count=0, corroboration_matches=[]
    )
    result = build_evidence(INCIDENT, verification, triage)
    assert result["assessment"]["verdict"] == "Likely Fake"


def test_contradiction_with_strong_support_yields_disputed_not_fake():
    """A single contradiction shouldn't overrule several other sources
    still actively supporting the report -- that goes to a human, it's
    not auto-labeled fake."""
    verification = full_verification(contradicts_evidence=True)
    triage = full_triage(ai_contradicts_evidence=True)
    result = build_evidence(INCIDENT, verification, triage)
    assert result["assessment"]["verdict"] == "Disputed -- Needs Human Review"


def test_negated_report_yields_resolved_verdict_not_fake():
    """A retracted/false-alarm report is not the same thing as a
    fabricated one -- it should be labeled Resolved, not Likely Fake."""
    verification = full_verification(negated=True)
    triage = full_triage(ai_negated=True, final_score=15, tier="Low")
    result = build_evidence(INCIDENT, verification, triage)
    assert result["assessment"]["verdict"] == "Resolved / False Alarm"


def test_no_evidence_either_way_yields_unverified_not_fake():
    """Lack of evidence is not proof of fakeness -- a report with no
    corroboration yet should read as Unverified, not Likely Fake."""
    result = build_evidence(
        {"report_text": "quiet", "location": "nowhere"},
        {"location_verified": False},
        {"keyword_hits": [], "tier": "Low", "confidence": 0.0},
    )
    assert result["assessment"]["verdict"] == "Unverified"


def test_verdict_appears_in_explanation_text():
    result = build_evidence(INCIDENT, full_verification(), full_triage())
    assert result["assessment"]["verdict"] in result["assessment"]["explanation"]


# ---------------------------------------------------------------------
# Recommendation logic
# ---------------------------------------------------------------------

def test_strong_high_severity_recommends_immediate_dispatch():
    result = build_evidence(INCIDENT, full_verification(), full_triage(tier="Critical", final_score=90))
    assert "dispatch" in result["assessment"]["recommendation"].lower()


def test_insufficient_evidence_recommends_hold():
    result = build_evidence(
        {"report_text": "quiet", "location": "nowhere"},
        {"location_verified": False},
        {"keyword_hits": [], "tier": "Low", "confidence": 0.0},
    )
    assert "hold" in result["assessment"]["recommendation"].lower()


def test_contradiction_routes_to_human_reviewer():
    verification = full_verification(contradicts_evidence=True)
    triage = full_triage(ai_contradicts_evidence=True)
    result = build_evidence(INCIDENT, verification, triage)
    assert "human reviewer" in result["assessment"]["recommendation"].lower()


# ---------------------------------------------------------------------
# Confidence: single source of truth
# ---------------------------------------------------------------------

def test_assessment_confidence_matches_triage_confidence():
    """The evidence engine must not compute a second, potentially
    disagreeing confidence number -- it explains triage's number."""
    triage = full_triage(confidence=0.73)
    result = build_evidence(INCIDENT, full_verification(), triage)
    assert result["assessment"]["confidence"] == 0.73


def test_missing_confidence_defaults_safely():
    result = build_evidence(INCIDENT, full_verification(), {"keyword_hits": ["fire"], "tier": "High"})
    assert result["assessment"]["confidence"] == 0.0


# ---------------------------------------------------------------------
# Sources / reasons / warnings
# ---------------------------------------------------------------------

def test_unavailable_ai_reasoning_shows_up_as_warning_not_silent():
    verification = full_verification(ai_available=False, ai_score=None, rationale="")
    triage = full_triage(ai_available=False, ai_rationale="")
    result = build_evidence(INCIDENT, verification, triage)
    assert any("ai reasoning" in w.lower() for w in result["warnings"])


def test_corroboration_reflected_as_supporting_source():
    reasons, warnings, sources = analyze_evidence(
        full_verification(corroboration_count=3),
        full_triage(corroboration_count=3),
        {"credibility": "High"},
    )
    corroboration = next(s for s in sources if s["name"] == "Corroboration")
    assert corroboration["status"] == "supports"
    assert any("independent" in r.lower() for r in reasons)


def test_gather_sources_returns_five_sources():
    sources = gather_sources(full_verification(), {"credibility": "High"})
    assert len(sources) == 7
    names = {s["name"] for s in sources}
    assert names == {"Location", "Weather / sensor", "Water level", "Seismic activity", "AI reasoning", "Corroboration", "Report credibility"}


def test_no_hazard_detected_is_a_warning():
    triage = full_triage(keyword_hits=[])
    result = build_evidence(INCIDENT, full_verification(), triage)
    assert any("no recognizable hazard" in w.lower() for w in result["warnings"])
    assert result["incident_type"] is None


# ---------------------------------------------------------------------
# credibility auto-computation
# ---------------------------------------------------------------------

def test_credibility_is_computed_when_not_supplied():
    result = build_evidence(INCIDENT, full_verification(), full_triage())
    assert "credibility" in result["credibility"]
    assert "score" in result["credibility"]


def test_explicit_credibility_overrides_autocompute():
    explicit = {"credibility": "Low", "score": 5, "reasons": ["forced"]}
    result = build_evidence(INCIDENT, full_verification(), full_triage(), credibility=explicit)
    assert result["credibility"] == explicit
