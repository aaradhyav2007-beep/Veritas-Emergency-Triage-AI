import requests
from datetime import datetime, timedelta

# Seismic magnitude and risk thresholds
SEISMIC_THRESHOLDS = {
    "minor": {"magnitude": 3.0, "boost": 5},
    "light": {"magnitude": 4.0, "boost": 15},
    "moderate": {"magnitude": 5.0, "boost": 25},
    "strong": {"magnitude": 6.0, "boost": 35},
    "major": {"magnitude": 7.0, "boost": 45},
}

# Proximity thresholds (in km)
PROXIMITY_THRESHOLDS = {
    "very_close": 25,      # < 25 km
    "close": 50,           # < 50 km
    "nearby": 100,         # < 100 km
    "regional": 250,       # < 250 km
}


def _calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate distance between two coordinates using Haversine formula.
    Returns distance in kilometers.
    """
    from math import radians, cos, sin, asin, sqrt
    
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    km = 6371 * c
    return km


def _calculate_seismic_risk(magnitude: float, distance_km: float, hours_ago: float) -> tuple:
    """
    Pure function: Calculate risk boost based on earthquake magnitude, distance, and recency.
    Returns (risk_boost, severity_level).
    """
    # Base risk from magnitude
    if magnitude >= SEISMIC_THRESHOLDS["major"]["magnitude"]:
        base_risk = SEISMIC_THRESHOLDS["major"]["boost"]
        severity = "major"
    elif magnitude >= SEISMIC_THRESHOLDS["strong"]["magnitude"]:
        base_risk = SEISMIC_THRESHOLDS["strong"]["boost"]
        severity = "strong"
    elif magnitude >= SEISMIC_THRESHOLDS["moderate"]["magnitude"]:
        base_risk = SEISMIC_THRESHOLDS["moderate"]["boost"]
        severity = "moderate"
    elif magnitude >= SEISMIC_THRESHOLDS["light"]["magnitude"]:
        base_risk = SEISMIC_THRESHOLDS["light"]["boost"]
        severity = "light"
    elif magnitude >= SEISMIC_THRESHOLDS["minor"]["magnitude"]:
        base_risk = SEISMIC_THRESHOLDS["minor"]["boost"]
        severity = "minor"
    else:
        return 0, "insignificant"
    
    # Reduce risk based on distance
    distance_factor = 1.0
    if distance_km > PROXIMITY_THRESHOLDS["regional"]:
        distance_factor = 0.3
    elif distance_km > PROXIMITY_THRESHOLDS["nearby"]:
        distance_factor = 0.6
    elif distance_km > PROXIMITY_THRESHOLDS["close"]:
        distance_factor = 0.8
    
    # Reduce risk based on time elapsed
    time_factor = 1.0
    if hours_ago > 72:
        time_factor = 0.2
    elif hours_ago > 24:
        time_factor = 0.5
    elif hours_ago > 6:
        time_factor = 0.8
    
    adjusted_risk = int(base_risk * distance_factor * time_factor)
    return adjusted_risk, severity


def get_recent_earthquakes(latitude: float, longitude: float, radius_deg: float = 2.0) -> dict:
    """
    Fetch recent earthquake data from USGS Earthquake Hazards Program API.
    """
    try:
        usgs_url = "https://earthquake.usgs.gov/fdsnws/event/1/query"

        # Look back 30 days from now, computed dynamically so this keeps
        # working after today -- a hardcoded date would silently narrow
        # (or eventually eliminate) the search window as time passes.
        start_time = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
        
        params = {
            "format": "geojson",
            "latitude": latitude,
            "longitude": longitude,
            "maxradius": radius_deg,
            "starttime": start_time,
            "minmagnitude": 2.5
        }
        
        response = requests.get(usgs_url, params=params, timeout=10)
        
        if response.status_code != 200:
            return {
                "available": False,
                "notes": f"USGS API error: {response.status_code} - {response.text[:100]}"
            }
        
        data = response.json()
        
        if "features" not in data or not data["features"]:
            return {
                "available": True,
                "earthquakes": [],
                "count": 0,
                "notes": "No recent earthquakes found in this region",
                "search_location": {
                    "latitude": latitude,
                    "longitude": longitude,
                    "radius_deg": radius_deg
                }
            }
        
        now = datetime.utcnow()
        earthquakes = []
        for feature in data["features"]:
            props = feature["properties"]
            coords = feature["geometry"]["coordinates"]
            
            eq_time = datetime.utcfromtimestamp(props["time"] / 1000)
            hours_ago = (now - eq_time).total_seconds() / 3600
            
            distance = _calculate_distance(
                latitude, longitude,
                coords[1], coords[0]
            )
            
            earthquakes.append({
                "magnitude": props.get("mag", 0),
                "depth_km": coords[2],
                "location": props.get("place", "Unknown"),
                "time": eq_time.isoformat(),
                "hours_ago": hours_ago,
                "distance_km": distance,
                "latitude": coords[1],
                "longitude": coords[0],
                "url": props.get("url", "")
            })
        
        # Sort by distance
        earthquakes.sort(key=lambda x: x["distance_km"])
        
        return {
            "available": True,
            "earthquakes": earthquakes,
            "count": len(earthquakes),
            "search_location": {
                "latitude": latitude,
                "longitude": longitude,
                "radius_deg": radius_deg
            }
        }
        
    except Exception as e:
        return {
            "available": False,
            "notes": f"Failed to fetch earthquake data: {str(e)}"
        }


def seismic_verify(
    location: str,
    latitude: float = None,
    longitude: float = None,
    hazard: str = None
) -> dict:
    """
    Verify earthquake/seismic risk by checking for recent seismic activity.
    """
    if latitude is None or longitude is None:
        return {
            "location_verified": False,
            "seismic_risk_boost": 0,
            "seismic_severity": "unknown",
            "notes": "Coordinates not provided for seismic verification"
        }
    
    seismic_data = get_recent_earthquakes(latitude, longitude)
    
    if not seismic_data.get("available"):
        return {
            "location_verified": True,
            "seismic_risk_boost": 0,
            "seismic_severity": "unknown",
            "live_seismic_data": None,
            "closest_earthquake": None,
            "notes": seismic_data.get("notes", "Seismic data unavailable"),
            "coordinates": {"latitude": latitude, "longitude": longitude}
        }
    
    earthquakes = seismic_data.get("earthquakes", [])
    if not earthquakes:
        return {
            "location_verified": True,
            "seismic_risk_boost": 0,
            "seismic_severity": "insignificant",
            "live_seismic_data": {"earthquakes": [], "count": 0},
            "closest_earthquake": None,
            "notes": "No recent significant earthquakes detected",
            "coordinates": {"latitude": latitude, "longitude": longitude}
        }
    
    closest_eq = earthquakes[0]
    risk_boost, severity = _calculate_seismic_risk(
        magnitude=closest_eq["magnitude"],
        distance_km=closest_eq["distance_km"],
        hours_ago=closest_eq["hours_ago"]
    )
    
    return {
        "location_verified": True,
        "seismic_risk_boost": risk_boost,
        "seismic_severity": severity,
        "live_seismic_data": {
            "earthquakes": earthquakes,
            "count": len(earthquakes),
            "search_location": seismic_data.get("search_location")
        },
        "closest_earthquake": closest_eq,
        "notes": f"Seismic activity verified using USGS API. Closest: M{closest_eq['magnitude']} "
                 f"{closest_eq['distance_km']:.1f}km away ({closest_eq['hours_ago']:.1f}h ago)",
        "coordinates": {"latitude": latitude, "longitude": longitude}
    }
