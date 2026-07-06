"""
Tests for the sensor-risk logic in skills/weather_geo_verify.py.

Only `_sensor_risk_boost` and the `SENSOR_TYPES` registry are tested here
-- they're pure functions/data with no network calls. `weather_geo_verify`
and `get_coordinates` themselves hit OpenStreetMap/Open-Meteo and are
intentionally left untested at the unit level (same pattern as the rest
of this codebase: network-touching code is exercised manually / via the
running app, not in the offline pytest suite).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skills.weather_geo_verify import SENSOR_TYPES, _sensor_risk_boost


def test_flood_above_threshold_boosts_risk():
    assert _sensor_risk_boost("flood", 61) == SENSOR_TYPES["flood"]["boost"]


def test_flood_at_or_below_threshold_no_boost():
    assert _sensor_risk_boost("flood", 60) == 0
    assert _sensor_risk_boost("flood", 10) == 0


def test_temp_above_threshold_boosts_risk():
    assert _sensor_risk_boost("temp", 46) == SENSOR_TYPES["temp"]["boost"]


def test_smoke_above_threshold_boosts_risk():
    """Regression test: 'smoke' used to be a selectable sensor type that
    had zero effect on the score. It must now actually contribute."""
    assert _sensor_risk_boost("smoke", 51) == SENSOR_TYPES["smoke"]["boost"]


def test_gas_above_threshold_boosts_risk():
    assert _sensor_risk_boost("gas", 41) == SENSOR_TYPES["gas"]["boost"]


def test_seismic_above_threshold_boosts_risk():
    assert _sensor_risk_boost("seismic", 41) == SENSOR_TYPES["seismic"]["boost"]


def test_structural_above_threshold_boosts_risk():
    assert _sensor_risk_boost("structural", 51) == SENSOR_TYPES["structural"]["boost"]


def test_unknown_sensor_type_never_raises_or_boosts():
    assert _sensor_risk_boost("barometric", 999) == 0
    assert _sensor_risk_boost("", 999) == 0
    assert _sensor_risk_boost(None, 999) == 0


def test_sensor_type_is_case_insensitive():
    assert _sensor_risk_boost("FLOOD", 100) == SENSOR_TYPES["flood"]["boost"]
    assert _sensor_risk_boost("Seismic", 100) == SENSOR_TYPES["seismic"]["boost"]


def test_all_sensor_types_have_required_fields():
    for key, entry in SENSOR_TYPES.items():
        assert "label" in entry
        assert "hazards" in entry and isinstance(entry["hazards"], list) and entry["hazards"]
        assert "threshold" in entry
        assert "boost" in entry
