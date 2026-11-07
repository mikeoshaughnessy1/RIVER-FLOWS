"""One time: save normals and yearly peaks from the full history, then cut the daily file to
config.START_DATE. Run it on the full file only. The full file stays in git history
(tag draft-heat-map-2026-11-06).

Usage: python scripts/trim_history.py
"""
import pathlib, sys
import pandas as pd
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import analytics as A, config, data_prep as dp

data = ROOT / 'data'
raw = pd.read_csv(data / 'daily_values.csv.gz', dtype=str)
if raw['date'].min() >= config.START_DATE:
    sys.exit('Already trimmed. Normals must come from the full history, so nothing was changed.')
df, _, _ = dp.build(raw, pd.read_csv(data / 'sites.csv', dtype=str))
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
