"""Rebuild data/daily_values.csv from the USGS Water Data API.

Usage:  USGS_API_KEY=... python scripts/fetch_usgs.py [start_date]
Full history is ~16 requests; without a key USGS may rate-limit you after a few.
"""
import os, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import config, usgs

if __name__ == '__main__':
    start = sys.argv[1] if len(sys.argv) > 1 else config.START_DATE
    daily = usgs.fetch_daily(list(config.SITES), start, None, os.environ.get('USGS_API_KEY'))
    out = pathlib.Path(__file__).resolve().parents[1] / 'data' / 'daily_values.csv'
    daily.to_csv(out, index=False)
    print(len(daily), 'daily rows ->', out)
