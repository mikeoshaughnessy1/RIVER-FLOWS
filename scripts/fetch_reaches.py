"""Download the main-stem river line upstream of each gauge (USGS NLDI, NHDPlus flowlines)
and save data/reaches.geojson. The map colors each reach by its gauge.

Each gauge gets up to MAX_KM of river above it. Where reaches overlap (a downstream gauge's
line runs past an upstream gauge), the map draws big rivers first and smaller gauges on top,
so every stretch ends up colored by the nearest gauge below it.

Usage: python scripts/fetch_reaches.py
"""
import json, sys, pathlib, time
import requests
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import config

URL = 'https://api.water.usgs.gov/nldi/linked-data/nwissite/USGS-{}/navigation/UM/flowlines'
MAX_KM = 150
DOWN_URL = 'https://api.water.usgs.gov/nldi/linked-data/nwissite/USGS-{}/navigation/DM/flowlines'
# Lowest gauge on a river: also draw the river below it, down to the confluence (km).
# These "below" lines are drawn first, so any other gauge's own reach covers them.
DOWNSTREAM_KM = {'06041000': 75, '06052500': 20, '06026210': 30, '06023000': 8, '06018500': 8,
                 '06033000': 45, '06195600': 5, '06048650': 30, '06050000': 25, '06192500': 30,
                 '12324200': 30, '06054500': 20, '06012500': 15}


def thin(coords, keep_every=3):
    pts = coords[::keep_every]
    if pts[-1] != coords[-1]:
        pts.append(coords[-1])
    return [[round(x, 4), round(y, 4)] for x, y in pts]


if __name__ == '__main__':
    feats = []
    for site in config.SITES:
        r = requests.get(URL.format(site), params={'distance': MAX_KM, 'f': 'json'}, timeout=120)
        r.raise_for_status()
        lines = [thin(f['geometry']['coordinates']) for f in r.json()['features']
                 if f['geometry']['type'] == 'LineString']
        feats.append({'type': 'Feature', 'properties': {'site_no': site, 'below': False, 'segments': len(lines)},
                      'geometry': {'type': 'MultiLineString', 'coordinates': lines}})
        print(site, config.SITES[site][1], len(lines), 'segments')
        km = DOWNSTREAM_KM.get(site)
        if km:
            r = requests.get(DOWN_URL.format(site), params={'distance': km, 'f': 'json'}, timeout=120)
            r.raise_for_status()
            down = [thin(f['geometry']['coordinates']) for f in r.json()['features']
                    if f['geometry']['type'] == 'LineString']
            feats.append({'type': 'Feature', 'properties': {'site_no': site, 'below': True, 'segments': len(down)},
                          'geometry': {'type': 'MultiLineString', 'coordinates': down}})
        time.sleep(0.3)
    out = pathlib.Path(__file__).resolve().parents[1] / 'data' / 'reaches.geojson'
    out.write_text(json.dumps({'type': 'FeatureCollection', 'features': feats}, separators=(',', ':')))
    print('saved', out, round(out.stat().st_size / 1e6, 2), 'MB')
