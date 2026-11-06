"""Download the main-stem river line upstream of each gauge (USGS NLDI, NHDPlus flowlines)
and save data/reaches.geojson. The map colors each reach by its gauge.

Each gauge gets up to MAX_KM of river above it. Where reaches overlap (a downstream gauge's
line runs past an upstream gauge), the map draws big rivers first and smaller gauges on top,
so every stretch ends up colored by the nearest gauge below it.

Usage: python scripts/fetch_reaches.py   (needs `pip install shapely` to stitch segments)
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
DEFAULT_DOWN_KM = 50
DOWNSTREAM_KM = {'06041000': 75, '06052500': 20, '06026210': 30, '06023000': 8, '06018500': 8,
                 '06033000': 45, '06195600': 5, '06048650': 30, '06050000': 25, '06192500': 30,
                 '12324200': 30, '06054500': 20, '06012500': 15}


def thin(coords, keep_every=4):
    pts = coords[::keep_every]
    if pts[-1] != coords[-1]:
        pts.append(coords[-1])
    return [[round(x, 3), round(y, 3)] for x, y in pts]


def get(url, km):
    for attempt in range(3):
        try:
            r = requests.get(url, params={'distance': km, 'f': 'json'}, timeout=120)
            r.raise_for_status()
            return [thin(f['geometry']['coordinates']) for f in r.json()['features']
                    if f['geometry']['type'] == 'LineString']
        except requests.RequestException:
            time.sleep(2 * (attempt + 1))
    print('  gave up on', url)
    return []


def one(site):
    up = get(URL.format(site), MAX_KM)
    down = get(DOWN_URL.format(site), DOWNSTREAM_KM.get(site, DEFAULT_DOWN_KM))
    return [{'type': 'Feature', 'properties': {'site_no': site, 'below': below},
             'geometry': {'type': 'MultiLineString', 'coordinates': lines}}
            for below, lines in ((False, up), (True, down)) if lines]


if __name__ == '__main__':
    from concurrent.futures import ThreadPoolExecutor
    from shapely.geometry import MultiLineString
    from shapely.ops import linemerge
    with ThreadPoolExecutor(6) as pool:
        feats = [f for fs in pool.map(one, list(config.SITES)) for f in fs]
    # NHD hands back thousands of short segments; stitch them into continuous lines so the
    # map draws smooth rivers instead of hatched ticks.
    for f in feats:
        merged = linemerge(MultiLineString(f['geometry']['coordinates']))
        parts = [merged] if merged.geom_type == 'LineString' else list(merged.geoms)
        f['geometry']['coordinates'] = [[[round(x, 3), round(y, 3)] for x, y in p.coords] for p in parts]
    out = pathlib.Path(__file__).resolve().parents[1] / 'data' / 'reaches.geojson'
    out.write_text(json.dumps({'type': 'FeatureCollection', 'features': feats}, separators=(',', ':')))
    print(len(feats), 'features for', len({f['properties']['site_no'] for f in feats}), 'gauges; saved',
          round(out.stat().st_size / 1e6, 2), 'MB')
