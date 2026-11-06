"""Download the main-stem river line upstream of each gauge (USGS NLDI, NHDPlus flowlines)
and save data/reaches.geojson. The map colors each reach by its gauge.

Each gauge claims up to MAX_KM of river above it (and a stretch below it). Every NHD segment
is then given to exactly ONE gauge, so no river is drawn twice:
  - a segment above one or more gauges goes to the gauge with the smallest drainage area among
    them, which is the nearest gauge below it;
  - a segment that is only below gauges goes to the one with the largest drainage area, which
    is the nearest gauge above it.
Drainage area (not flow) because it always grows downstream; flow can drop below a dam or
diversion. A gauge with no published area gets one estimated from its flow, for ordering only.
Drawing each stretch once avoids the "zipper" look two slightly different copies made.

Usage: python scripts/fetch_reaches.py   (needs `pip install shapely` to stitch segments)
"""
import json, sys, pathlib, time
import requests
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import config

URL = 'https://api.water.usgs.gov/nldi/linked-data/nwissite/USGS-{}/navigation/UM/flowlines'
MAX_KM = 150
SIMPLIFY_DEG = 0.0009   # about 70-100 m in Montana
DOWN_URL = 'https://api.water.usgs.gov/nldi/linked-data/nwissite/USGS-{}/navigation/DM/flowlines'
# Lowest gauge on a river: also draw the river below it, down to the confluence (km).
# These "below" lines are drawn first, so any other gauge's own reach covers them.
DEFAULT_DOWN_KM = 50
DOWNSTREAM_KM = {'06041000': 75, '06052500': 20, '06026210': 30, '06023000': 8, '06018500': 8,
                 '06033000': 45, '06195600': 5, '06048650': 30, '06050000': 25, '06192500': 30,
                 '12324200': 30, '06054500': 20, '06012500': 15}


def thin(coords, keep_every=1):
    pts = coords[::keep_every]
    if pts[-1] != coords[-1]:
        pts.append(coords[-1])
    return [[x, y] for x, y in pts]


def get(url, km):
    """{comid: coords} for the flowlines NLDI returns."""
    for attempt in range(3):
        try:
            r = requests.get(url, params={'distance': km, 'f': 'json'}, timeout=120)
            r.raise_for_status()
            return {f['properties']['nhdplus_comid']: f['geometry']['coordinates'] for f in r.json()['features']
                    if f['geometry']['type'] == 'LineString'}
        except requests.RequestException:
            time.sleep(2 * (attempt + 1))
    print('  gave up on', url)
    return {}


def one(site):
    return site, get(URL.format(site), MAX_KM), get(DOWN_URL.format(site), DOWNSTREAM_KM.get(site, DEFAULT_DOWN_KM))


def drainage_rank():
    """Drainage area (sq mi) per gauge for ordering. Missing areas are estimated from mean flow
    using area-per-cfs from gauges on the same river (or all gauges if none)."""
    import pandas as pd
    root = pathlib.Path(__file__).resolve().parents[1] / 'data'
    sites = pd.read_csv(root / 'sites.csv', dtype={'site_no': str})
    flow = pd.read_csv(root / 'daily_values.csv.gz', dtype={'site_no': str},
                       usecols=['site_no', 'flow_cfs']).groupby('site_no')['flow_cfs'].mean()
    sites = sites.set_index('site_no')
    area = pd.to_numeric(sites['drain_area'], errors='coerce')
    ratio = (area / flow.reindex(area.index).clip(lower=0.1)).dropna()
    by_river = ratio.groupby(sites.loc[ratio.index, 'river']).median()   # same river first: runoff per
    est = {}                                                             # square mile varies a lot by basin
    for s in area[area.isna()].index:
        r = by_river.get(sites.loc[s, 'river'], ratio.median())
        est[s] = float(flow.get(s, 0) or 0) * r
    return area.fillna(pd.Series(est)).to_dict()


if __name__ == '__main__':
    from concurrent.futures import ThreadPoolExecutor
    from shapely.geometry import MultiLineString
    from shapely.ops import linemerge
    import pickle
    cache = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None    # optional: reuse a download
    if cache and cache.exists():
        got = pickle.loads(cache.read_bytes())
    else:
        with ThreadPoolExecutor(6) as pool:
            got = list(pool.map(one, list(config.SITES)))
        if cache:
            cache.write_bytes(pickle.dumps(got))
    flow = drainage_rank()
    geom, up_claims, down_claims = {}, {}, {}
    for site, up, down in got:
        for c, g in up.items():
            geom[c] = g
            up_claims.setdefault(c, []).append(site)
        for c, g in down.items():
            geom.setdefault(c, g)
            down_claims.setdefault(c, []).append(site)
    owned = {}            # site -> {'up': [coords], 'down': [coords]}
    for c, g in geom.items():
        if c in up_claims:
            site, part = min(up_claims[c], key=lambda s: flow.get(s, 0)), 'up'
        else:
            site, part = max(down_claims[c], key=lambda s: flow.get(s, 0)), 'down'
        owned.setdefault(site, {'up': [], 'down': []})[part].append(g)
    feats = []
    for site, parts in owned.items():
        for part, lines in parts.items():
            if not lines:
                continue
            merged = linemerge(MultiLineString(lines))
            # Smooth by simplifying to ~70-100 m (keeps bends, drops noise)
            merged = merged.simplify(SIMPLIFY_DEG, preserve_topology=False)
            geoms = [merged] if merged.geom_type == 'LineString' else list(merged.geoms)
            coords = [[[round(x, 4), round(y, 4)] for x, y in g.coords] for g in geoms if len(g.coords) > 1]
            if coords:
                feats.append({'type': 'Feature', 'properties': {'site_no': site, 'below': part == 'down'},
                              'geometry': {'type': 'MultiLineString', 'coordinates': coords}})
    out = pathlib.Path(__file__).resolve().parents[1] / 'data' / 'reaches.geojson'
    out.write_text(json.dumps({'type': 'FeatureCollection', 'features': feats}, separators=(',', ':')))
    print(len(geom), 'segments,', len(feats), 'features for', len(owned), 'gauges; saved',
          round(out.stat().st_size / 1e6, 2), 'MB')
