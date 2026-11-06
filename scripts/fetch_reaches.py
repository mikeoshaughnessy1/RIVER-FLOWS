"""Download the main-stem river line upstream of each gauge (USGS NLDI, NHDPlus flowlines)
and save data/reaches.geojson. The map colors each reach by its gauge.

Each gauge gets up to MAX_KM of river above it, and NHD segments are then claimed once:
every stretch belongs to the nearest gauge below it. Drawing two gauges' copies of the same
stretch on top of each other made the lower one peek out, so lines looked hatched.

Usage: python scripts/fetch_reaches.py   (needs `pip install shapely` to stitch segments)
"""
import csv, json, sys, pathlib, time
import requests
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import config

URL = 'https://api.water.usgs.gov/nldi/linked-data/nwissite/USGS-{}/navigation/UM/flowlines'
MAX_KM = 150
SIMPLIFY_DEG = 0.0012   # about 100 m in Montana; points cost map speed, smoothing hides the corners
SMOOTH_ROUNDS = 2       # Chaikin corner cutting after simplifying
DOWN_URL = 'https://api.water.usgs.gov/nldi/linked-data/nwissite/USGS-{}/navigation/DM/flowlines'
# Lowest gauge on a river: also draw the river below it, down to the confluence (km).
# These "below" lines are drawn first, so any other gauge's own reach covers them.
DEFAULT_DOWN_KM = 50
DOWNSTREAM_KM = {'06041000': 75, '06052500': 20, '06026210': 30, '06023000': 8, '06018500': 8,
                 '06033000': 45, '06195600': 5, '06048650': 30, '06050000': 25, '06192500': 30,
                 '12324200': 30, '06054500': 20, '06012500': 15}


def get(url, km):
    """Return {NHD segment id: coordinates}."""
    for attempt in range(3):
        try:
            r = requests.get(url, params={'distance': km, 'f': 'json'}, timeout=120)
            r.raise_for_status()
            return {f['properties']['nhdplus_comid']: f['geometry']['coordinates'] for f in r.json()['features']
                    if f['geometry']['type'] == 'LineString'}
        except requests.RequestException:
            time.sleep(2 * (attempt + 1))
    sys.exit(f'Gave up on {url}. Nothing was saved, so the old river lines stay in place.')


def one(site):
    return [{'site_no': site, 'below': False, 'segments': get(URL.format(site), MAX_KM)},
            {'site_no': site, 'below': True,
             'segments': get(DOWN_URL.format(site), DOWNSTREAM_KM.get(site, DEFAULT_DOWN_KM))}]


def claim(reaches, area):
    """Give every NHD segment to one gauge. A gauge's own reach beats any "below" stretch, and
    among own reaches the smallest river wins, which is the nearest gauge below that stretch.
    Among "below" stretches the biggest river wins, so its color carries past a confluence."""
    taken = set()
    for r in sorted(reaches, key=lambda r: (r['below'], area[r['site_no']] * (-1 if r['below'] else 1))):
        r['segments'] = {k: v for k, v in r['segments'].items() if k not in taken}
        taken |= r['segments'].keys()
    return [r for r in reaches if r['segments']]


def chaikin(pts, rounds=SMOOTH_ROUNDS):
    """Round off corners. The two end points stay put, so neighboring reaches still meet."""
    for _ in range(rounds):
        if len(pts) < 3:
            return pts
        mid = []
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            mid += [(.75 * x0 + .25 * x1, .75 * y0 + .25 * y1), (.25 * x0 + .75 * x1, .25 * y0 + .75 * y1)]
        pts = [pts[0]] + mid[1:-1] + [pts[-1]]
    return pts


if __name__ == '__main__':
    from concurrent.futures import ThreadPoolExecutor
    from shapely.geometry import MultiLineString
    from shapely.ops import linemerge
    root = pathlib.Path(__file__).resolve().parents[1]
    with open(root / 'data' / 'sites.csv', newline='') as f:
        area = {r['site_no']: float(r['drain_area'] or 0) for r in csv.DictReader(f)}
    with ThreadPoolExecutor(6) as pool:
        reaches = claim([r for rs in pool.map(one, list(config.SITES)) for r in rs], area)
    feats = []
    for r in reaches:
        # NHD hands back thousands of short segments; stitch them into continuous lines.
        merged = linemerge(MultiLineString(list(r['segments'].values())))
        merged = merged.simplify(SIMPLIFY_DEG, preserve_topology=False)
        parts = [merged] if merged.geom_type == 'LineString' else list(merged.geoms)
        lines = [[[round(x, 5), round(y, 5)] for x, y in chaikin([c[:2] for c in p.coords])]
                 for p in parts if len(p.coords) > 1]
        feats.append({'type': 'Feature', 'properties': {'site_no': r['site_no'], 'below': r['below']},
                      'geometry': {'type': 'MultiLineString', 'coordinates': lines}})
    out = root / 'data' / 'reaches.geojson'
    out.write_text(json.dumps({'type': 'FeatureCollection', 'features': feats}, separators=(',', ':')))
    print(len(feats), 'features for', len({f['properties']['site_no'] for f in feats}), 'gauges;',
          sum(len(l) for f in feats for l in f['geometry']['coordinates']), 'points; saved',
          round(out.stat().st_size / 1e6, 2), 'MB')
