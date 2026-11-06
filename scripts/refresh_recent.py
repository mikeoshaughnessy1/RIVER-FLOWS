"""Save recent USGS readings to data/recent.csv.gz: the last REFRESH_DAYS, and every day since the
snapshot ended if that is longer. The app lays this small file over the big snapshot, so it grows
about 190 rows a day until a new snapshot is pulled. The daily GitHub Action runs this. A failed download raises and saves nothing,
so the last good file stays in place.

Usage: python scripts/refresh_recent.py   (USGS_API_KEY in the environment is optional)
"""
import gzip, json, os, pathlib, sys
import pandas as pd
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import config, data_prep, usgs

now = pd.Timestamp.now(tz='America/Denver')
snapshot = json.loads((ROOT / 'data' / 'snapshot.json').read_text())
start = data_prep.refresh_start(snapshot['downloaded'], now.date())
fresh = usgs.fetch_daily(list(config.SITES), start, None, os.environ.get('USGS_API_KEY'))
fresh['date'] = fresh['date'].dt.strftime('%Y-%m-%d')
(ROOT / 'data' / 'recent.csv.gz').write_bytes(gzip.compress(fresh.to_csv(index=False).encode(), mtime=0))
(ROOT / 'data' / 'recent.json').write_text(json.dumps({'downloaded': now.isoformat(timespec='minutes')}) + '\n')
print(len(fresh), 'rows from', fresh['date'].min(), 'to', fresh['date'].max())
