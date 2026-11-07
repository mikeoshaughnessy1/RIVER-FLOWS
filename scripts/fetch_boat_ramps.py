"""Save Montana FWP boat ramps for trailered boats to data/boat_ramps.csv (name, lat, lon, boat_fac).

Keeps every ramp. Drops hand launches and raft slides.
Usage: python scripts/fetch_boat_ramps.py
"""
import pathlib
import pandas as pd
import requests

URL = 'https://services3.arcgis.com/Cdxz8r11hT0MGzg1/arcgis/rest/services/FWPLND_FAS_POINTS/FeatureServer/0/query'
r = requests.get(URL, params={'where': '1=1', 'outFields': 'NAME,BOAT_FAC', 'outSR': 4326, 'f': 'geojson'}, timeout=60)
r.raise_for_status()
rows = [{'name': f['properties']['NAME'], 'lat': round(f['geometry']['coordinates'][1], 5),
         'lon': round(f['geometry']['coordinates'][0], 5), 'boat_fac': f['properties']['BOAT_FAC']}
        for f in r.json()['features']
        if f.get('geometry') and 'Ramp' in (f['properties']['BOAT_FAC'] or '')]
out = pathlib.Path(__file__).resolve().parents[1] / 'data' / 'boat_ramps.csv'
pd.DataFrame(rows).sort_values('name').to_csv(out, index=False)
print(len(rows), 'ramps saved')
