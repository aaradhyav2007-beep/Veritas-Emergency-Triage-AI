import requests

# ---------------------------------------------------------------------
# Sensor types
#
# Each entry maps a sensor reading to the hazard category it's evidence
# for, plus the threshold/boost used by `_sensor_risk_boost`. Kept as a
# plain dict (rather than inline if-statements) so it's a single source
# of truth for both the risk calculation and anything that wants to list
# valid sensor types (e.g. the Streamlit dropdown).
#
# All sensor_value readings are treated as a normalized 0-100 intensity
# scale for that sensor (e.g. flood = % of expected water level, smoke =
# particulate/opacity index, seismic = shake-intensity index).
# ---------------------------------------------------------------------
SENSOR_TYPES = {
    "smoke": {
        "label": "Smoke / particulate",
        "hazards": ["fire", "smoke"],
        "threshold": 50,
        "boost": 20,
    },
    "flood": {
        "label": "Flood / water level",
        "hazards": ["flood", "tsunami"],
        "threshold": 60,
        "boost": 25,
    },
    "temp": {
        "label": "Temperature",
        "hazards": ["fire"],
        "threshold": 45,
        "boost": 20,
    },
    "gas": {
        "label": "Gas / combustible vapor",
        "hazards": ["explosion", "fire"],
        "threshold": 40,
        "boost": 30,
    },
    "seismic": {
        "label": "Seismic activity",
        "hazards": ["earthquake", "tsunami", "landslide"],
        "threshold": 40,
        "boost": 30,
    },
    "structural": {
        "label": "Structural stress / vibration",
        "hazards": ["collapse"],
        "threshold": 50,
        "boost": 25,
    },
}


def _sensor_risk_boost(sensor_type: str, sensor_value: float) -> int:
    """
    Pure function, no network calls: how much risk a single sensor
    reading adds, based on SENSOR_TYPES. Returns 0 for an unknown/blank
    sensor type or a reading below its threshold.
    """
    entry = SENSOR_TYPES.get((sensor_type or "").lower())
    if entry is None:
        return 0
    if sensor_value > entry["threshold"]:
        return entry["boost"]
    return 0


def get_coordinates(location: str):
    url = "https://nominatim.openstreetmap.org/search"

    params = {
        "q": location,
        "format": "json",
        "limit": 1
    }

    headers = {
        "User-Agent": "VeritasAI/1.0"
    }

    try:
        response = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
    except (requests.exceptions.RequestException, ValueError):
        # Network failure, timeout, non-2xx status, or non-JSON body --
        # treat exactly like "location not found" so callers fail closed
        # instead of crashing the whole pipeline.
        return None

    if not data:
        return None

    return float(data[0]["lat"]), float(data[0]["lon"])


def weather_geo_verify(
    location: str,
    sensor_type: str,
    sensor_value: float,
    hazard: str = None
):
    coords = get_coordinates(location)

    if coords is None:
        return {
            "location_verified": False,
            "weather_risk_boost": 0,
            "notes": "Location not found"
        }

    lat, lon = coords

    weather_url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}"
        f"&longitude={lon}"
        "&current=temperature_2m,precipitation,wind_speed_10m"
    )

    try:
        weather_response = requests.get(weather_url, timeout=10)
        weather_response.raise_for_status()
        weather = weather_response.json()["current"]
    except (requests.exceptions.RequestException, ValueError, KeyError):
        # Location was verified but live weather is unavailable -- still
        # report the verified location/coordinates, just without a
        # weather-based risk boost, rather than raising and losing the
        # location verification we already have.
        return {
            "location_verified": True,
            "weather_risk_boost": _sensor_risk_boost(sensor_type, sensor_value),
            "coordinates": {
                "latitude": lat,
                "longitude": lon
            },
            "live_weather": None,
            "notes": "Location verified, but live weather data unavailable"
        }

    risk = 0

    if weather["precipitation"] > 5:
        risk += 20

    if weather["wind_speed_10m"] > 40:
        risk += 20

    risk += _sensor_risk_boost(sensor_type, sensor_value)

    return {
        "location_verified": True,
        "weather_risk_boost": risk,
        "coordinates": {
            "latitude": lat,
            "longitude": lon
        },
        "live_weather": weather,
        "notes": "Verified using OpenStreetMap + Open-Meteo"
    }