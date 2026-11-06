"""Independent check: plain pandas on the raw CSV, no app code. Compare with what the app shows.

Usage: python scripts/independent_check.py [path/to/daily_values.csv]
"""
import sys
import pandas as pd

path = sys.argv[1] if len(sys.argv) > 1 else 'data/daily_values.csv'
d = pd.read_csv(path, dtype={'site_no': str}, parse_dates=['date'])
print(f'rows {len(d):,}   gauges {d.site_no.nunique()}   {d.date.min().date()} to {d.date.max().date()}')
print(f'total of all daily flows: {d.flow_cfs.sum():,.0f} cfs-days')

last = d[d.date == d.date.max()].set_index('site_no')['flow_cfs']
print('\nlatest flow by gauge:')
print(last.to_string())

g = d[d.site_no == '06043500'].copy()
g['md'] = g.date.dt.strftime('%m-%d')
g['wy'] = g.date.dt.year + (g.date.dt.month >= 10)
today = g.iloc[-1]
hist = g[(g.md == today.md) & (g.wy != today.wy)]['flow_cfs']
print(f'\nGallatin nr Gateway {today.date.date()}: {today.flow_cfs:.0f} cfs, median for {today.md} '
      f'over {hist.size} other years = {hist.median():.0f}, {today.flow_cfs / hist.median() * 100:.0f}% of median')

l = d[(d.site_no == '06052500') & (d.date.dt.year == 2021)]
print(f'Gallatin at Logan 2021 days with max temp >= 73F: {int((l.temp_max_c * 9 / 5 + 32 >= 73).sum())}')
j = d[(d.site_no == '06036650') & (d.date.dt.year == 2025)]
print(f'Jefferson 2025 days below 500 cfs: {int((j.flow_cfs < 500).sum())}')
y = d[(d.site_no == '06192500') & (d.date.between('2021-10-01', '2022-09-30'))]
print(f'Yellowstone nr Livingston WY2022 peak: {y.flow_cfs.max():,.0f} cfs on {y.loc[y.flow_cfs.idxmax(), "date"].date()}')
