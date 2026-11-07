"""Save normals and yearly peaks from the full history, then cut the daily file to
config.START_DATE. It needs the full file, which stays in git history. To rerun:
    git show draft-heat-map-2026-11-06:data/daily_values.csv.gz > data/daily_values.csv.gz
    python scripts/trim_history.py
shortcut: normals stop at the tag's date, so they miss newer years. Rerun on a fresh full pull
every few years if that matters.
"""
import pathlib, sys
import pandas as pd
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import analytics as A, config, data_prep as dp

A.NORMALS, A.PEAKS = {}, {}      # compute from the full rows, not from the last saved tables
data = ROOT / 'data'
sites = pd.read_csv(data / 'sites.csv', dtype=str)
raw = pd.read_csv(data / 'daily_values.csv.gz', dtype=str)
raw = raw[raw['site_no'].isin(sites['site_no'])]
if raw['date'].min() >= config.START_DATE:
    sys.exit('Already trimmed. Normals must come from the full history, so nothing was changed.')
df, _, _ = dp.build(raw, sites)
last_wy = int(df['water_year'].max())
normals, peaks = [], []
for site in df['site_no'].cat.categories:
    g = A._gauge(df, site)
    if g.empty:
        continue
    n = A.daily_normals(g, last_wy).round(2).rename_axis('md').reset_index()
    normals.append(n.assign(site_no=site))
    r = A.annual_peaks(df, site)
    if not r.error:
        peaks.append(pd.DataFrame(r.value).assign(site_no=site))
pd.concat(normals).to_csv(data / 'normals.csv.gz', index=False)
pd.concat(peaks).to_csv(data / 'peaks.csv.gz', index=False)
kept = raw[raw['date'] >= config.START_DATE]
kept.to_csv(data / 'daily_values.csv.gz', index=False)
print(len(raw), 'rows cut to', len(kept))
