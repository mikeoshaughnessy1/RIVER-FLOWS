"""Client for the USGS Water Data API (api.waterdata.usgs.gov, OGC API "daily" collection).

The old waterservices.usgs.gov service is being retired (Nov 2026 to Feb 2027), so the app
only talks to the new API. Without an API key USGS allows only a few requests per hour;
put a free key in Streamlit secrets as USGS_API_KEY (signup: api.waterdata.usgs.gov/signup).

Returns tidy pandas tables in the app's own column names. No app logic in here.
"""
from __future__ import annotations
import pandas as pd
import requests
import config

DAILY_URL = 'https://api.waterdata.usgs.gov/ogcapi/v0/collections/daily/items'
UA = 'bozeman-river-report (student project)'

# New-API qualifier words -> the short flags the app shows
FLAG_NAMES = {'ESTIMATED': 'Estimated', 'ICE': 'Ice', 'EQUIPMENT': 'Equipment',
              'SEASONAL': 'Seasonal', 'FLOOD': 'Flood', 'BACKWATER': 'Backwater'}


def _pages(params: dict, api_key: str | None, max_pages: int = 60):
    headers = {'User-Agent': UA}
    if api_key:
        headers['X-Api-Key'] = api_key
    url, first = DAILY_URL, True
    for _ in range(max_pages):
        r = requests.get(url, params=params if first else None, headers=headers, timeout=90)
        if r.status_code == 429:
            raise RuntimeError('USGS rate limit reached. Add a free USGS API key (USGS_API_KEY) '
                               'or try again in an hour.')
        r.raise_for_status()
        js = r.json()
        yield js.get('features', [])
        nxt = [l['href'] for l in js.get('links', []) if l.get('rel') == 'next']
        if not nxt:
            return
        url, first = nxt[0], False


def fetch_daily(site_nos: list[str], start: str, end: str | None = None,
                api_key: str | None = None) -> pd.DataFrame:
    """Daily mean flow plus daily mean and max water temp, one row per site per day,
    in the same columns as data/daily_values.csv."""
    params = {
        'f': 'json', 'skipGeometry': 'true', 'limit': 10000,
        'monitoring_location_id': ','.join('USGS-' + s for s in site_nos),
        'parameter_code': '00060,00010', 'statistic_id': '00003,00001',
        'time': f'{start}/{end or ".."}',
        'properties': 'monitoring_location_id,parameter_code,statistic_id,time,value,'
                      'approval_status,qualifier',
    }
    rows = []
    for feats in _pages(params, api_key):
        for f in feats:
            p = f['properties']
            col = config.PARAMS.get((p['parameter_code'], p['statistic_id']))
            if col:
                rows.append((p['monitoring_location_id'].replace('USGS-', ''), p['time'], col,
                             p['value'], p['approval_status'], p.get('qualifier') or []))
    if not rows:
        raise ValueError('USGS returned no daily values for those sites and dates.')
    long = pd.DataFrame(rows, columns=['site_no', 'date', 'col', 'value', 'status', 'qual'])
    long['value'] = pd.to_numeric(long['value'], errors='coerce')
    long['flags'] = long['qual'].map(lambda q: ' '.join(FLAG_NAMES.get(x, x.title()) for x in q))
    # A site can report two sensors for one parameter on one day; keep the first non-null value
    long = long.sort_values('value', na_position='last').drop_duplicates(['site_no', 'date', 'col'])
    return to_wide(long)


def to_wide(long: pd.DataFrame) -> pd.DataFrame:
    vals = long.pivot(index=['site_no', 'date'], columns='col', values='value')
    out = vals.reindex(columns=config.VALUE_COLS)
    flow = long[long['col'] == 'flow_cfs'].set_index(['site_no', 'date'])
    temp = long[long['col'] == 'temp_mean_c'].set_index(['site_no', 'date'])
    out['flow_status'] = flow['status']
    out['flow_flags'] = flow['flags']
    out['temp_status'] = temp['status']
    out = out.reset_index()
    out['date'] = pd.to_datetime(out['date'])
    return out.sort_values(['site_no', 'date']).reset_index(drop=True)[config.DAILY_COLUMNS]
