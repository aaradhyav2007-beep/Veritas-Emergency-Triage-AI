"""
Tests for skills/incident_credibility.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skills.incident_credibility import assess_incident_credibility


DETAILED_REPORT = "Large fire reported near MG Road with heavy smoke and visible flames."
SHORT_REPORT = "fire"


def test_all_signals_present_yields_high_credibility():
    verification = {
        "location_verified": True,
        "live_weather": {"temperature_2m": 31, "precipitation": 0, "wind_speed_10m": 5},
    }
    result = assess_incident_credibility(DETAILED_REPORT, verification, ["fire"])
    assert result["credibility"] == "High"
    assert result["score"] == 90


def test_no_signals_yields_low_credibility():
    result = assess_incident_credibility(SHORT_REPORT, {}, [])
    assert result["credibility"] == "Low"
    assert result["score"] == 0


def test_partial_signals_yield_medium_credibility():
    """Location + weather + detail, but no recognized hazard keyword,
    lands in the Medium band (40 + 20 + 10 = 70)."""
    verification = {
        "location_verified": True,
        "live_weather": {"temperature_2m": 31, "precipitation": 0, "wind_speed_10m": 5},
    }
    result = assess_incident_credibility(DETAILED_REPORT, verification, [])
    assert result["credibility"] == "Medium"
    assert result["score"] == 60


def test_reasons_reflect_missing_location():
    result = assess_incident_credibility(DETAILED_REPORT, {}, ["fire"])
    assert any("could not be verified" in r.lower() for r in result["reasons"])


def test_reasons_reflect_missing_hazard():
    result = assess_incident_credibility(DETAILED_REPORT, {"location_verified": True}, [])
    assert any("no recognizable hazard" in r.lower() for r in result["reasons"])


def test_short_report_flagged_as_limited_detail():
    result = assess_incident_credibility(SHORT_REPORT, {"location_verified": True}, ["fire"])
    assert any("limited details" in r.lower() for r in result["reasons"])


def test_output_has_expected_keys():
    result = assess_incident_credibility(DETAILED_REPORT, {}, [])
    assert {"credibility", "score", "reasons"}.issubset(result.keys())
