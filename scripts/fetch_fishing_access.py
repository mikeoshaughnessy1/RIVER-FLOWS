"""Save Montana FWP fishing access sites to data/fishing_access.csv (name, lat, lon).

Usage: python scripts/fetch_fishing_access.py
"""
import pathlib
import pandas as pd
import requests

URL = 'https://services3.arcgis.com/Cdxz8r11hT0MGzg1/arcgis/rest/services/FWPLND_FAS_POINTS/FeatureServer/0/query'
r = requests.get(URL, params={'where': '1=1', 'outFields': '*', 'outSR': 4326, 'f': 'geojson'}, timeout=60)
r.raise_for_status()
feats = r.json()['features']
name = next(k for k in feats[0]['properties'] if k.upper() in ('NAME', 'SITENAME', 'FAS_NAME', 'SITE_NAME'))
rows = [{'name': f['properties'][name], 'lat': round(f['geometry']['coordinates'][1], 5),
         'lon': round(f['geometry']['coordinates'][0], 5)} for f in feats if f.get('geometry')]
out = pathlib.Path(__file__).resolve().parents[1] / 'data' / 'fishing_access.csv'
pd.DataFrame(rows).sort_values('name').to_csv(out, index=False)
print(len(rows), 'sites saved')
