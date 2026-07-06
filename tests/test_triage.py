"""
Tests for agents/triage_agent.py.

These tests pass `verification` dicts directly into run_triage rather than
going through run_verification, so they exercise the triage scoring/
confidence logic in isolation -- no network calls (weather, geocoding,
Gemini) are made.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.triage_agent import run_triage


FIRE_REPORT = {
    "report_text": "There is heavy smoke and possible forest fire near Central School.",
    "sensor_value": 72.0,
}

NO_HAZARD_REPORT = {
    "report_text": "Everything looks calm and quiet here today.",
    "sensor_value": 10.0,
}


def base_verification(**overrides):
    """A fully-populated, 'everything succeeded' verification dict."""
    v = {
        "location_verified": True,
        "weather_risk_boost": 0,
        "live_weather": {"temperature_2m": 25, "precipitation": 0, "wind_speed_10m": 5},
        "ai_available": True,
        "ai_score": 80,
        "ai_confidence": 0.9,
        "negated": False,
        "contradicts_evidence": False,
        "rationale": "Consistent with reported hazard.",
        "corroboration_count": 0,
        "corroboration_boost": 0,
        "matches": [],
    }
    v.update(overrides)
    return v


# ---------------------------------------------------------------------
# ai_score None-handling
# ---------------------------------------------------------------------

def test_ai_score_none_falls_back_to_rule_score():
    """When the AI pass didn't run, ai_score is None and the LLM term in
    combine_scores should fall back to the rule score, not silently
    default to some other constant."""
    verification = base_verification(ai_available=False, ai_score=None, ai_confidence=0.0)
    result = run_triage(FIRE_REPORT, verification)

    assert result["ai_score"] is None
    assert result["final_score"] > 0
    assert result["ai_available"] is False


def test_ai_score_present_is_used_directly():
    verification = base_verification(ai_score=95)
    result = run_triage(FIRE_REPORT, verification)
    assert result["ai_score"] == 95


# ---------------------------------------------------------------------
# Negation cap
# ---------------------------------------------------------------------

def test_negated_report_caps_final_score():
    """If the AI determines the report negates/retracts the hazard
    ('fire is out'), final_score must be capped at 20 regardless of how
    high the keyword/AI scores were."""
    verification = base_verification(ai_score=95, negated=True)
    result = run_triage(FIRE_REPORT, verification)

    assert result["final_score"] <= 20
    assert result["tier"] == "Low"
    assert result["ai_negated"] is True


def test_non_negated_report_is_not_capped():
    verification = base_verification(ai_score=95, negated=False)
    result = run_triage(FIRE_REPORT, verification)
    assert result["final_score"] > 20


# ---------------------------------------------------------------------
# AI-unavailable confidence penalty
# ---------------------------------------------------------------------

def test_ai_unavailable_reduces_confidence_vs_available():
    """A report with identical evidence should score strictly lower
    confidence when the AI pass didn't run than when it did -- otherwise
    a missing evidence source is invisible to the confidence metric."""
    verification_with_ai = base_verification()
    verification_without_ai = base_verification(
        ai_available=False, ai_score=None, ai_confidence=0.0
    )

    with_ai = run_triage(FIRE_REPORT, verification_with_ai)
    without_ai = run_triage(FIRE_REPORT, verification_without_ai)

    assert without_ai["confidence"] < with_ai["confidence"]


def test_confidence_never_exceeds_100_percent_even_with_all_signals():
    """All five evidence signals maxed out should not push confidence
    above 1.0, even though the raw point total can exceed 100."""
    verification = base_verification(
        ai_score=100, ai_confidence=1.0, corroboration_count=3, corroboration_boost=20
    )
    result = run_triage(FIRE_REPORT, verification)
    assert result["confidence"] <= 1.0


def test_confidence_never_negative():
    """Even with every signal absent/penalized, confidence should clamp
    at 0, not go negative."""
    verification = {
        "location_verified": False,
        "live_weather": None,
        "ai_available": False,
        "corroboration_count": 0,
        "corroboration_boost": 0,
    }
    result = run_triage(NO_HAZARD_REPORT, verification)
    assert result["confidence"] >= 0.0


def test_ai_contradicts_evidence_reduces_confidence():
    base = base_verification()
    contradicted = base_verification(contradicts_evidence=True)

    clean = run_triage(FIRE_REPORT, base)
    flagged = run_triage(FIRE_REPORT, contradicted)

    assert flagged["confidence"] < clean["confidence"]
    assert flagged["ai_contradicts_evidence"] is True

def test_image_path_does_not_break_triage():
    # This test ensures that the presence of an image_path in the incident dict
    # does not cause a crash or unexpected behavior in the triage agent.
    # The triage agent itself doesn't directly process the image, but it passes
    # it to the verification agent, which then passes it to AI reasoning.
    # We'll simulate a verification dict that reflects AI reasoning having processed an image.
    incident_with_image = FIRE_REPORT.copy()
    incident_with_image["image_path"] = "/path/to/test_image.jpg"

    verification_with_image_ai = base_verification(
        ai_available=True,
        ai_score=80,
        ai_confidence=0.85,
        rationale="AI reasoning considered the image and found it consistent with the report."
    )
    result = run_triage(incident_with_image, verification_with_image_ai)

    assert result["final_score"] > 0
    assert result["confidence"] > 0
    assert result["ai_available"] is True
    assert "image_path" not in result # image_path should not be in the final triage result


# ---------------------------------------------------------------------
# Corroboration
# ---------------------------------------------------------------------

def test_corroboration_boost_increases_final_score():
    no_corroboration = base_verification()
    with_corroboration = base_verification(
        corroboration_count=2,
        corroboration_boost=16,
        matches=[
            {"location": "Nearby St", "distance_km": 1.2, "report_text": "Saw fire too"},
        ],
    )

    plain = run_triage(FIRE_REPORT, no_corroboration)
    corroborated = run_triage(FIRE_REPORT, with_corroboration)

    assert corroborated["final_score"] >= plain["final_score"]
    assert corroborated["corroboration_count"] == 2
    assert corroborated["corroboration_matches"][0]["location"] == "Nearby St"


def test_weather_and_corroboration_boost_combined_is_capped():
    """combine_scores should never receive more than 20 points of
    combined external boost (weather + corroboration), even if their
    sum individually exceeds that."""
    verification = base_verification(weather_risk_boost=20, corroboration_boost=20)

    # Sanity-check against a verification with no external boost at all,
    # holding everything else equal -- the capped run should score the
    # same as if boost were exactly 20, not 40.
    capped_at_20 = base_verification(weather_risk_boost=20, corroboration_boost=0)

    result_double_boost = run_triage(FIRE_REPORT, verification)
    result_single_boost = run_triage(FIRE_REPORT, capped_at_20)

    assert result_double_boost["final_score"] == result_single_boost["final_score"]


def test_no_corroboration_matches_by_default():
    result = run_triage(FIRE_REPORT, base_verification())
    assert result["corroboration_count"] == 0
    assert result["corroboration_matches"] == []


# ---------------------------------------------------------------------
# Hazard detection / resources / tiering
# ---------------------------------------------------------------------

def test_keyword_hits_detected_for_fire_report():
    result = run_triage(FIRE_REPORT, base_verification())
    assert "fire" in result["keyword_hits"]
    assert "smoke" in result["keyword_hits"]


def test_no_hazard_report_yields_no_hits_and_low_tier():
    verification = base_verification(ai_score=10, ai_confidence=0.2)
    result = run_triage(NO_HAZARD_REPORT, verification)
    assert result["keyword_hits"] == []
    assert result["tier"] in ("Low", "Medium")


def test_resources_match_tier():
    critical_verification = base_verification(ai_score=100, weather_risk_boost=20)
    result = run_triage(FIRE_REPORT, critical_verification)

    from skills.resource_mapper import map_resources
    assert result["resources"] == map_resources(result["tier"])


def test_severity_tier_thresholds_are_consistent_with_final_score():
    result = run_triage(FIRE_REPORT, base_verification())
    score = result["final_score"]
    tier = result["tier"]

    if tier == "Critical":
        assert score >= 80
    elif tier == "High":
        assert 60 <= score < 80
    elif tier == "Medium":
        assert 30 <= score < 60
    else:
        assert score < 30


# ---------------------------------------------------------------------
# Output contract: keys main.py / orchestrator.py rely on
# ---------------------------------------------------------------------

def test_run_triage_output_has_expected_keys():
    result = run_triage(FIRE_REPORT, base_verification())
    expected_keys = {
        "rule_score", "ai_score", "final_score", "tier", "confidence",
        "keyword_hits", "resources", "ai_available", "ai_rationale",
        "ai_negated", "ai_contradicts_evidence", "corroboration_count",
        "corroboration_matches",
    }
    assert expected_keys.issubset(result.keys())


def test_missing_optional_verification_fields_do_not_crash():
    """run_triage should tolerate a minimal verification dict (e.g. from
    a location-verification failure) without raising KeyError."""
    minimal_verification = {"location_verified": False}
    result = run_triage(FIRE_REPORT, minimal_verification)
    assert isinstance(result["final_score"], int)
    assert result["ai_available"] is False
