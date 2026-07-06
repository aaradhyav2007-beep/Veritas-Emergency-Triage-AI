import requests
from datetime import datetime, timedelta

# Water level risk thresholds and boost values
WATER_LEVEL_THRESHOLDS = {
    "low": {"discharge_threshold": 50, "boost": 5},
    "moderate": {"discharge_threshold": 100, "boost": 15},
    "high": {"discharge_threshold": 200, "boost": 25},
    "critical": {"discharge_threshold": 500, "boost": 35},
}


def _calculate_water_level_risk(river_discharge: float) -> tuple:
    """
    Pure function: Calculate risk boost based on river discharge rate.
    Returns (risk_boost, severity_level).
    
    Args:
        river_discharge: Current river discharge in m³/s
    
    Returns:
        Tuple of (risk_boost: int, severity_level: str)
    """
    if river_discharge >= WATER_LEVEL_THRESHOLDS["critical"]["discharge_threshold"]:
        return WATER_LEVEL_THRESHOLDS["critical"]["boost"], "critical"
    elif river_discharge >= WATER_LEVEL_THRESHOLDS["high"]["discharge_threshold"]:
        return WATER_LEVEL_THRESHOLDS["high"]["boost"], "high"
    elif river_discharge >= WATER_LEVEL_THRESHOLDS["moderate"]["discharge_threshold"]:
        return WATER_LEVEL_THRESHOLDS["moderate"]["boost"], "moderate"
    elif river_discharge >= WATER_LEVEL_THRESHOLDS["low"]["discharge_threshold"]:
        return WATER_LEVEL_THRESHOLDS["low"]["boost"], "low"
    return 0, "normal"


def get_water_level_data(latitude: float, longitude: float) -> dict:
    """
    Fetch current river discharge data from Open-Meteo Flood API.
    
    Args:
        latitude: Location latitude
        longitude: Location longitude
    
    Returns:
        Dictionary with river discharge data or error information
    """
    try:
        flood_url = (
            "https://flood-api.open-meteo.com/v1/flood"
            f"?latitude={latitude}"
            f"&longitude={longitude}"
            "&daily=river_discharge"
        )
        
        response = requests.get(flood_url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if "daily" not in data or not data["daily"].get("river_discharge"):
            return {
                "available": True,
                "current_discharge": 0,
                "next_7_days": [0] * 7,
                "timestamps": [datetime.now().isoformat()] * 7,
                "notes": "No significant river discharge detected at this location",
                "location": {"latitude": latitude, "longitude": longitude}
            }
        
        # Get current (today's) discharge
        current_discharge = data["daily"]["river_discharge"][0]
        
        # Get forecast data
        forecast_data = {
            "current_discharge": current_discharge,
            "next_7_days": data["daily"]["river_discharge"][:7],
            "timestamps": data["daily"]["time"][:7],
            "available": True,
            "location": {
                "latitude": data.get("latitude"),
                "longitude": data.get("longitude")
            }
        }
        
        return forecast_data
        
    except requests.exceptions.RequestException as e:
        return {
            "available": False,
            "notes": f"Failed to fetch water level data: {str(e)}"
        }
    except (KeyError, ValueError) as e:
        return {
            "available": False,
            "notes": f"Invalid response format from water level API: {str(e)}"
        }


def water_level_verify(
    location: str,
    latitude: float = None,
    longitude: float = None,
    hazard: str = None
) -> dict:
    """
    Verify flood risk by checking current river discharge levels.
    
    This function queries the Open-Meteo Flood API to get real-time
    river discharge data and calculates a risk boost based on current
    water levels.
    
    Args:
        location: Location name (for reference/logging)
        latitude: Location latitude (required for API call)
        longitude: Location longitude (required for API call)
        hazard: Hazard type (e.g., "flood", "tsunami") for context
    
    Returns:
        Dictionary with water level verification results:
        {
            "location_verified": bool,
            "water_level_risk_boost": int (0-35),
            "water_level_severity": str ("normal", "low", "moderate", "high", "critical"),
            "live_water_data": dict with current and forecast discharge,
            "notes": str,
            "coordinates": {"latitude": float, "longitude": float}
        }
    """
    
    # If coordinates not provided, return early
    if latitude is None or longitude is None:
        return {
            "location_verified": False,
            "water_level_risk_boost": 0,
            "water_level_severity": "unknown",
            "notes": "Coordinates not provided for water level verification"
        }
    
    # Fetch water level data
    water_data = get_water_level_data(latitude, longitude)
    
    if not water_data.get("available"):
        return {
            "location_verified": True,
            "water_level_risk_boost": 0,
            "water_level_severity": "unknown",
            "live_water_data": None,
            "notes": water_data.get("notes", "Water level data unavailable"),
            "coordinates": {
                "latitude": latitude,
                "longitude": longitude
            }
        }
    
    # Calculate risk based on current discharge
    current_discharge = water_data.get("current_discharge", 0)
    risk_boost, severity = _calculate_water_level_risk(current_discharge)
    
    return {
        "location_verified": True,
        "water_level_risk_boost": risk_boost,
        "water_level_severity": severity,
        "live_water_data": {
            "current_discharge_m3s": current_discharge,
            "next_7_days_forecast": water_data.get("next_7_days"),
            "forecast_timestamps": water_data.get("timestamps"),
            "location": water_data.get("location")
        },
        "notes": f"Water level verified using Open-Meteo Flood API. Current discharge: {current_discharge:.2f} m³/s ({severity})",
        "coordinates": {
            "latitude": latitude,
            "longitude": longitude
        }
    }
