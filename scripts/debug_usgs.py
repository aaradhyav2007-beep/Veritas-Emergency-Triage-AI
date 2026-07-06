import requests
from datetime import datetime, timedelta

def debug_usgs():
    url = "https://earthquake.usgs.gov/fdsnws/event/1/query"
    now = datetime.utcnow()
    # Use a date that is definitely in the past relative to 2026-07-05
    start_time = "2026-06-01"
    
    params = {
        "format": "geojson",
        "latitude": 34.0522,
        "longitude": -118.2437,
        "maxradius": 2,
        "starttime": start_time,
        "minmagnitude": 2.5
    }
    
    print(f"Requesting: {url}")
    print(f"Params: {params}")
    
    response = requests.get(url, params=params)
    print(f"Status: {response.status_code}")
    if response.status_code != 200:
        print(f"Error: {response.text}")
    else:
        print("Success!")
        print(f"Found: {len(response.json()['features'])} events")

if __name__ == "__main__":
    debug_usgs()
