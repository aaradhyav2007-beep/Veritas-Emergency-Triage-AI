import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skills.water_level_verify import water_level_verify
from skills.seismic_verify import seismic_verify
from agents.verification_agent import run_verification
from agents.triage_agent import run_triage

def test_water_level():
    print("\n--- Testing Water Level Verification ---")
    # New Orleans coordinates
    lat, lon = 29.9511, -90.0715
    result = water_level_verify("New Orleans", lat, lon)
    print(f"Location: New Orleans ({lat}, {lon})")
    print(f"Risk Boost: {result.get('water_level_risk_boost')}")
    print(f"Severity: {result.get('water_level_severity')}")
    print(f"Notes: {result.get('notes')}")

def test_seismic():
    print("\n--- Testing Seismic Verification ---")
    # Los Angeles coordinates
    lat, lon = 34.0522, -118.2437
    result = seismic_verify("Los Angeles", lat, lon)
    print(f"Location: Los Angeles ({lat}, {lon})")
    print(f"Risk Boost: {result.get('seismic_risk_boost')}")
    print(f"Severity: {result.get('seismic_severity')}")
    print(f"Notes: {result.get('notes')}")
    if result.get("closest_earthquake"):
        print(f"Closest EQ: M{result['closest_earthquake']['magnitude']} at {result['closest_earthquake']['distance_km']:.1f}km")

def test_full_pipeline():
    print("\n--- Testing Full Verification Pipeline ---")
    incident = {
        "report_text": "Massive earthquake hit downtown Los Angeles, buildings are shaking!",
        "location": "Los Angeles, CA",
        "sensor_type": "seismic",
        "sensor_value": 85.0
    }
    
    print(f"Processing incident: {incident['report_text']}")
    verification = run_verification(incident)
    triage = run_triage(incident, verification)
    
    print(f"Final Score: {triage['final_score']}")
    print(f"Tier: {triage['tier']}")
    print(f"Confidence: {triage['confidence']:.2%}")
    print(f"Seismic Boost: {triage.get('seismic_risk_boost')}")
    print(f"Water Boost: {triage.get('water_level_risk_boost')}")
    print(f"Weather Boost: {verification.get('weather_risk_boost')}")

if __name__ == "__main__":
    try:
        test_water_level()
        test_seismic()
        test_full_pipeline()
    except Exception as e:
        print(f"Error during testing: {e}")
        import traceback
        traceback.print_exc()
