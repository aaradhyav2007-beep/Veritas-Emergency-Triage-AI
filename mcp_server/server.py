import sys
from pathlib import Path

# Add the project root to Python's module search path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP
from skills.weather_geo_verify import weather_geo_verify

mcp = FastMCP("veritas-verification")

@mcp.tool()
def verify_location_weather(location: str, sensor_type: str = "", sensor_value: float = 0) -> dict:
    """Verify an incident location and check live weather risk using
    OpenStreetMap (geocoding) and Open-Meteo (current weather)."""
    return weather_geo_verify(location, sensor_type, sensor_value)


if __name__ == "__main__":
    mcp.run()
