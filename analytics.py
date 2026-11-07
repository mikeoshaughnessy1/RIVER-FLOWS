"""All the river math. Pure functions: dataframe + explicit arguments in, a result dict out.

Every tool returns the same contract:
    {tool, value, definition, scope, rows_used, caveats, error}
An unknown gauge or a bad date returns `error` with the valid options. Nothing is guessed.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
import pathlib
import pandas as pd
import config

MIN_NORMAL_YEARS = 5          # need at least this many other years to call something "normal"
FULL_YEAR_DAYS = 330          # a water year with fewer flow days than this is "partial"
STEADY_PCT = 5                # a 7-day change inside this is steady
MIN_CHANGE_CFS = 1.0          # below this, percent change is not reported


@dataclass
class ToolResult:
    tool: str
    value: object = None
    definition: str = ''
    scope: str = ''
    rows_used: int = 0
    caveats: list = field(default_factory=list)
    error: str | None = None

    def to_dict(self):
        return asdict(self)


# ---------- argument checking ----------

def _site(df, site):
    """Accept a site number or an exact gauge label. Return (site_no, label, error)."""
    labels = pd.Series({k: g['label'].iloc[0] for k, g in _groups(df).items()})
    if site in labels.index:
        return site, labels[site], None
    hit = labels[labels.str.lower() == str(site).strip().lower()]
    if len(hit) == 1:
        return hit.index[0], hit.iloc[0], None
    return None, None, (f'Gauge "{site}" not found. Valid gauges: '
                        + '; '.join(f'{k} ({v})' for k, v in labels.items()))


def _dates(df, start, end):
    lo, hi = df['date'].min(), df['date'].max()
    try:
        s = pd.Timestamp(start) if start else lo
        e = pd.Timestamp(end) if end else hi
    except (ValueError, TypeError):
        return None, None, f'Could not read the dates "{start}" / "{end}". Use YYYY-MM-DD.'
    if s > e:
        return None, None, f'Start date {s.date()} is after end date {e.date()}.'
    if e < lo or s > hi:
        return None, None, f'No data in that window. Loaded data runs {lo.date()} to {hi.date()}.'
    return s, e, None


_GROUPS: dict = {}


def _groups(df):
    """Rows for each gauge, split once per loaded table (scanning 1.5M rows per gauge is slow)."""
    key = (id(df), len(df))
    groups = _GROUPS.get(key)      # a local, because another visitor's thread can clear _GROUPS at any moment
    if groups is None:
        if len(_GROUPS) >= 2:      # each split is a full table in memory; the app caches 2 tables
            _GROUPS.clear()
        groups = {k: g for k, g in df.groupby('site_no', observed=True, sort=False)}
        _GROUPS[key] = groups
    return groups


def _gauge(df, site_no):
    g = _groups(df).get(site_no)
    return g if g is not None else df.iloc[0:0]


def _fmt_window(s, e):
    return f'{s.date()} to {e.date()}'


def _years_note(df_site, col='flow_cfs'):
    yrs = df_site.loc[df_site[col].notna(), 'water_year'].nunique()
    return yrs


# ---------- normals ----------

_DATA = pathlib.Path(__file__).resolve().parent / 'data'


def _by_site(name: str, index=None) -> dict:
    """A saved table from scripts/trim_history.py, split by gauge. Empty if the file is missing."""
    path = _DATA / name
    if not path.exists():
        return {}
    t = pd.read_csv(path, dtype={'site_no': str, 'md': str})
    return {s: (g.set_index(index) if index else g).drop(columns='site_no') for s, g in t.groupby('site_no')}


NORMALS = _by_site('normals.csv.gz', 'md')    # all years, so normal stays strong with 5 years of daily rows
PEAKS = _by_site('peaks.csv.gz')


def daily_normals(g: pd.DataFrame, exclude_wy: int | None, col='flow_cfs') -> pd.DataFrame:
    """Median and 10th/25th/75th/90th percentiles of a column for each calendar day (MM-DD),
    across every water year except `exclude_wy`. Feb 29 borrows from Feb 28.
    shortcut: saved flow normals include past years a viewer may be looking at, a small effect
    over 25 years. Upgrade by saving a table per year if that ever matters."""
    if col == 'flow_cfs' and len(g) and g['site_no'].iloc[0] in NORMALS:
        return NORMALS[g['site_no'].iloc[0]]
    hist = g[g['water_year'] != exclude_wy] if exclude_wy else g
    hist = hist[hist[col].notna()]
    if hist.empty:   # brand-new gauge: no other years yet
        return pd.DataFrame(columns=['p10', 'p25', 'median', 'p75', 'p90', 'years'])
    md = hist['md'].replace('02-29', '02-28')
    q = hist.groupby(md)[col].quantile([.1, .25, .5, .75, .9]).unstack()
    q.columns = ['p10', 'p25', 'median', 'p75', 'p90']
    q['years'] = hist.groupby(md)['water_year'].nunique()
    return q


def _pct_rank(value, history):
    history = history.dropna()
    if not len(history):
        return None
    return float((history < value).mean() * 100)


# ---------- tools ----------

def list_gauges(df) -> ToolResult:
    g = (df.groupby(['site_no', 'label', 'river'])
           .agg(first=('date', 'min'), last=('date', 'max'),
                flow_days=('flow_cfs', 'count'), temp_days=('temp_max_c', 'count'))
           .reset_index())
    g['first'] = g['first'].dt.date.astype(str)
    g['last'] = g['last'].dt.date.astype(str)
    return ToolResult('list_gauges', g.to_dict('records'),
                      'Every gauge loaded, with its period of record and days with data.',
                      'All gauges', len(df))


def current_conditions(df, sites: list | None = None, as_of: str | None = None) -> ToolResult:
    """Latest daily mean flow per gauge, compared with the median for that calendar day."""
    caveats, out, used = [], [], 0
    site_nos = []
    for s in (sites or list(_groups(df))):
        sn, _, err = _site(df, s)
        if err:
            return ToolResult('current_conditions', error=err)
        site_nos.append(sn)
    cutoff = pd.Timestamp(as_of) if as_of else df['date'].max()
    for sn in site_nos:
        full = _gauge(df, sn)
        g = full[(full['date'] <= cutoff) & full['flow_cfs'].notna()]
        if g.empty:
            continue
        last = g.iloc[-1]
        norms = daily_normals(full, last['water_year'])
        md = '02-28' if last['md'] == '02-29' else last['md']
        n = norms.loc[md] if md in norms.index else None
        week = g[g['date'] == last['date'] - pd.Timedelta(days=7)]
        prior = full[(full['md'] == last['md']) & (full['water_year'] != last['water_year'])]
        temps = full[(full['date'] <= last['date']) & (full['date'] > last['date'] - pd.Timedelta(days=3))
                     & full['temp_max_f'].notna()]
        row = {
            'site_no': sn, 'gauge': last['label'], 'river': last['river'],
            'date': str(last['date'].date()), 'flow_cfs': float(last['flow_cfs']),
            'median_cfs': None if n is None else float(n['median']),
            'pct_of_median': None, 'percentile': _pct_rank(last['flow_cfs'], prior['flow_cfs']),
            'years_of_record': None if n is None else int(n['years']),
            'change_7d_pct': None if week.empty or not week['flow_cfs'].iloc[0]
                             else float((last['flow_cfs'] / week['flow_cfs'].iloc[0] - 1) * 100),
            'water_temp_max_f': None if temps.empty else float(temps.iloc[-1]['temp_max_f']),
            'water_temp_mean_f': None if temps.empty else float(temps.iloc[-1]['temp_mean_f']),
            'status': last['flow_status'], 'flags': last['flow_flags'],
        }
        # Normal under 1 cfs makes percents meaningless (0.02 cfs normal -> "29,833%")
        if n is not None and n['median'] >= MIN_CHANGE_CFS:
            row['pct_of_median'] = float(last['flow_cfs'] / n['median'] * 100)
        if n is None or n['years'] < MIN_NORMAL_YEARS:
            caveats.append(f'{last["label"]}: fewer than {MIN_NORMAL_YEARS} other years of record, '
                           f'so "normal" is shaky.')
        if row['flags']:
            caveats.append(f'{last["label"]}: latest value flagged {row["flags"]}.')
        out.append(row)
        used += len(g)
    stale = [r['gauge'] for r in out if pd.Timestamp(r['date']) < cutoff - pd.Timedelta(days=3)]
    if stale:
        caveats.append('Not current (no flow in the last 3 days of the data): ' + ', '.join(stale))
    return ToolResult('current_conditions', out,
                      'Latest daily mean flow (cfs). Median = median of the same calendar day in '
                      'every other water year on record at that gauge. Percentile = share of those '
                      'past days that were lower. Water temp = most recent daily max/mean within 3 days.',
                      f'As of {cutoff.date()}', used, caveats)


def _flow_note(pct):
    if pct is None:
        return ''
    return 'Running low for the date.' if pct < 75 else ('Running high for the date.' if pct > 130 else 'Near normal for the date.')


def _temp_note(temp):
    if temp is not None and temp >= config.HOOT_OWL_F:
        return f'Water at {temp:.0f}°F, at or above the {config.HOOT_OWL_F:.0f}°F line.'
    if temp is not None and temp >= config.HOOT_OWL_F - 5:
        return f'Water at {temp:.0f}°F, close to the {config.HOOT_OWL_F:.0f}°F line.'
    return ''


def _river_temp(row):
    """Water max at a gauge, or None on hot springs: that water is not river water."""
    return None if row.get('site_no') in config.THERMAL else row.get('water_temp_max_f')


def river_note(row: dict) -> ToolResult:
    """One plain line about a current_conditions row: flow for the date, and water temp near the
    73 F line. Facts only. FWP makes the actual call on restrictions."""
    text = ' '.join(x for x in (_flow_note(row.get('pct_of_median')), _temp_note(_river_temp(row))) if x)
    return ToolResult('river_note', text, 'Flow vs the normal for the date, and water temp vs the FWP line.',
                      row.get('gauge', ''), 1)


def river_summary(rows: list) -> ToolResult:
    """One plain line for a whole river, from the current_conditions rows of its gauges with a
    recent reading. Gauges that disagree are called mixed. Temp comes from the warmest gauge."""
    definition = 'Flow vs the normal for the date at each gauge, and the warmest gauge vs the FWP line.'
    if not rows:
        return ToolResult('river_summary', 'No reading in the last 3 days.', definition)
    flow = {_flow_note(r.get('pct_of_median')) for r in rows} - {''}
    temps = [t for t in map(_river_temp, rows) if t is not None]
    bits = [flow.pop() if len(flow) == 1 else ('Mixed for the date: gauges differ.' if flow else 'No normal for the date.'),
            _temp_note(max(temps) if temps else None)]
    return ToolResult('river_summary', ' '.join(x for x in bits if x), definition, rows[0].get('river', ''), len(rows))


def verdict(rows: list, where: str) -> ToolResult:
    """One headline from current_conditions rows: which way most gauges moved over 7 days."""
    definition = f'Most means over half of gauges with a 7-day change moved more than {STEADY_PCT}% that way.'
    ch = [r['change_7d_pct'] for r in rows if r.get('change_7d_pct') is not None]
    if not ch:
        return ToolResult('verdict', f'No recent 7-day change for {where}.', definition)
    moves = {'dropping': sum(c < -STEADY_PCT for c in ch), 'rising': sum(c > STEADY_PCT for c in ch)}
    moves['steady'] = len(ch) - moves['dropping'] - moves['rising']
    word, n = max(moves.items(), key=lambda kv: kv[1])
    say = f'Most {where} rivers are {word}.' if n > len(ch) / 2 else f'{where} rivers are mixed this week.'
    return ToolResult('verdict', say, definition, where, len(ch))


def flow_stats(df, site, start=None, end=None) -> ToolResult:
    sn, label, err = _site(df, site)
    if err:
        return ToolResult('flow_stats', error=err)
    s, e, err = _dates(df, start, end)
    if err:
        return ToolResult('flow_stats', error=err)
    g = _gauge(df, sn)
    g = g[(g['date'] >= s) & (g['date'] <= e)]
    f = g['flow_cfs'].dropna()
    if f.empty:
        return ToolResult('flow_stats', error=f'No flow data for {label} between {_fmt_window(s, e)}.')
    days = (e - s).days + 1
    caveats = []
    if len(f) < days:
        caveats.append(f'{days - len(f)} of {days} days in the window have no flow value.')
    est = (g['flow_flags'].str.contains('Estimated') & g['flow_cfs'].notna()).sum()
    if est:
        caveats.append(f'{int(est)} day(s) are USGS estimates (often ice in winter).')
    value = {'mean_cfs': float(f.mean()), 'median_cfs': float(f.median()),
             'min_cfs': float(f.min()), 'min_date': str(g.loc[f.idxmin(), 'date'].date()),
             'max_cfs': float(f.max()), 'max_date': str(g.loc[f.idxmax(), 'date'].date()),
             'days_with_data': int(len(f)),
             'volume_acre_ft': float(f.sum() * 1.9835)}
    return ToolResult('flow_stats', value,
                      'Statistics of daily mean flow (cfs). Volume = sum of daily means x 1.9835 '
                      '(1 cfs for one day = 1.9835 acre-feet).',
                      f'{label}, {_fmt_window(s, e)}', len(g), caveats)


def compare_to_normal(df, site, start, end) -> ToolResult:
    """Mean flow over a window vs the same calendar window in every other year."""
    sn, label, err = _site(df, site)
    if err:
        return ToolResult('compare_to_normal', error=err)
    s, e, err = _dates(df, start, end)
    if err:
        return ToolResult('compare_to_normal', error=err)
    if (e - s).days > 365:
        return ToolResult('compare_to_normal', error='Use a window of one year or less.')
    g = _gauge(df, sn)
    now = g[(g['date'] >= s) & (g['date'] <= e)]['flow_cfs'].dropna()
    if now.empty:
        return ToolResult('compare_to_normal', error=f'No flow for {label} in {_fmt_window(s, e)}.')
    others = []
    for shift in range(1, 200):
        ps, pe = s - pd.DateOffset(years=shift), e - pd.DateOffset(years=shift)
        if pe < g['date'].min():
            break
        w = g[(g['date'] >= ps) & (g['date'] <= pe)]['flow_cfs'].dropna()
        if len(w) >= 0.9 * ((pe - ps).days + 1):
            others.append({'year': int(ps.year), 'mean_cfs': float(w.mean())})
    caveats = []
    if len(others) < MIN_NORMAL_YEARS:
        caveats.append(f'Only {len(others)} comparable year(s) on record; treat "normal" loosely.')
    if not others:
        return ToolResult('compare_to_normal', error=f'No earlier years to compare at {label}.')
    hist = pd.Series([o['mean_cfs'] for o in others])
    if hist.median() < MIN_CHANGE_CFS:
        caveats.append(f'Percent of normal is left blank because normal flow is under {MIN_CHANGE_CFS:g} cfs.')
    value = {'window_mean_cfs': float(now.mean()), 'median_of_other_years_cfs': float(hist.median()),
             'pct_of_median': float(now.mean() / hist.median() * 100) if hist.median() >= MIN_CHANGE_CFS else None,
             'rank': f'{int((hist > now.mean()).sum()) + 1} of {len(hist) + 1} (1 = highest)',
             'years_compared': len(others), 'wettest': max(others, key=lambda o: o['mean_cfs']),
             'driest': min(others, key=lambda o: o['mean_cfs'])}
    return ToolResult('compare_to_normal', value,
                      'Mean daily flow in the window vs the median of the same calendar window in each '
                      'earlier year with at least 90% of days present.',
                      f'{label}, {_fmt_window(s, e)}', int(len(now)), caveats)


def annual_peaks(df, site, water_years: list | None = None) -> ToolResult:
    """Peak daily mean flow and its date for each water year (runoff size and timing)."""
    sn, label, err = _site(df, site)
    if err:
        return ToolResult('annual_peaks', error=err)
    g = _gauge(df, sn).dropna(subset=['flow_cfs'])
    if water_years:
        bad = [y for y in water_years if y not in set(g['water_year'])]
        if bad:
            return ToolResult('annual_peaks', error=f'Water year(s) {bad} not in the data for {label}. '
                              f'Available: {g["water_year"].min()}-{g["water_year"].max()}.')
        g = g[g['water_year'].isin(water_years)]
    rows, partial = [], []
    for wy, w in g.groupby('water_year'):
        i = w['flow_cfs'].idxmax()
        d = w.loc[i, 'date']
        rows.append({'water_year': int(wy), 'peak_cfs': float(w.loc[i, 'flow_cfs']),
                     'peak_date': str(d.date()), 'peak_day_of_year': int(d.dayofyear),
                     'days_with_data': int(len(w))})
        if len(w) < FULL_YEAR_DAYS:
            partial.append(int(wy))
    caveats = []
    if partial:
        caveats.append(f'Partial water year(s) {partial}: the true peak may be missing.')
    caveats.append('Daily mean peaks are lower than the instantaneous peaks USGS publishes.')
    return ToolResult('annual_peaks', rows,
                      'Highest daily mean flow in each water year (Oct 1 to Sep 30) and the date it hit.',
                      label, len(g), caveats)


def runoff_timing_trend(df, site) -> ToolResult:
    """Is the peak coming earlier? Straight-line trend of peak day-of-year across full years."""
    r = annual_peaks(df, site)
    if r.error:
        return ToolResult('runoff_timing_trend', error=r.error)
    p = PEAKS.get(str(site), pd.DataFrame(r.value))     # the saved table reaches back past the 5 kept years
    p = p[p['days_with_data'] >= FULL_YEAR_DAYS]
    if len(p) < 8:
        return ToolResult('runoff_timing_trend', error='Need at least 8 full water years for a trend.')
    x, y = p['water_year'], p['peak_day_of_year']
    slope = float(((x - x.mean()) * (y - y.mean())).sum() / ((x - x.mean()) ** 2).sum())
    r2 = float(x.corr(y) ** 2)
    value = {'years': len(p), 'first_year': int(x.min()), 'last_year': int(x.max()),
             'median_peak_date': pd.Timestamp('2001-01-01') + pd.Timedelta(days=int(y.median()) - 1),
             'days_per_decade': slope * 10, 'r_squared': r2}
    value['median_peak_date'] = value['median_peak_date'].strftime('%b %d')
    caveats = ['A straight line through ~25 noisy years; low R-squared means weather swamps any trend.',
               'Correlation over time is not proof of a cause (snowpack, dams and irrigation all matter).']
    if 'Madison' in r.scope or 'Ennis' in r.scope:
        caveats.append('The Madison is dam-regulated (Hebgen, Ennis), so timing is partly managed.')
    return ToolResult('runoff_timing_trend', value,
                      'Least-squares slope of the peak day-of-year against water year, full years only. '
                      'Negative = peaks arriving earlier.', r.scope, r.rows_used, caveats)


def monthly_flow(df, site, water_years: list | None = None) -> ToolResult:
    sn, label, err = _site(df, site)
    if err:
        return ToolResult('monthly_flow', error=err)
    g = _gauge(df, sn).dropna(subset=['flow_cfs'])
    if water_years:
        g = g[g['water_year'].isin(water_years)]
        if g.empty:
            return ToolResult('monthly_flow', error=f'No flow for {label} in water years {water_years}.')
    m = g.groupby('month')['flow_cfs'].agg(['mean', 'median', 'count']).reset_index()
    m['month'] = pd.to_datetime(m['month'], format='%m').dt.strftime('%b')
    m.columns = ['month', 'mean_cfs', 'median_cfs', 'days']
    yrs = 'all years' if not water_years else f'water years {min(water_years)}-{max(water_years)}'
    return ToolResult('monthly_flow', m.to_dict('records'),
                      'Mean and median of daily mean flow by calendar month.',
                      f'{label}, {yrs}', len(g))


def hot_water_days(df, site, year: int, threshold_f: float = config.HOOT_OWL_F) -> ToolResult:
    """Days the daily max water temp hit the threshold, and runs of 3+ days in a row."""
    sn, label, err = _site(df, site)
    if err:
        return ToolResult('hot_water_days', error=err)
    g = _gauge(df, sn)
    g = g[(g['year'] == int(year))]
    t = g.dropna(subset=['temp_max_f'])
    if t.empty:
        has = _gauge(df, sn).dropna(subset=['temp_max_f'])['year'].unique()
        msg = (f'{label} has no water temperature for {year}. '
               + (f'Temperature years available: {sorted(int(y) for y in has)}.' if len(has)
                  else 'This gauge has no temperature sensor in the loaded data.'))
        alt = df[(df['year'] == int(year)) & df['temp_max_f'].notna()]['label'].unique()
        if len(alt):
            msg += f' Gauges with {year} water temps: {", ".join(sorted(alt))}.'
        return ToolResult('hot_water_days', error=msg)
    hot = t['temp_max_f'] >= threshold_f
    runs, start, prev = [], None, None
    for d, h in zip(t['date'], hot):
        if h and start is not None and prev is not None and (d - prev).days == 1:
            prev = d
        elif h:
            if start is not None:
                runs.append((start, prev))
            start, prev = d, d
        else:
            if start is not None:
                runs.append((start, prev))
            start, prev = None, None
    if start is not None:
        runs.append((start, prev))
    long_runs = [(a, b) for a, b in runs if (b - a).days + 1 >= config.HOOT_OWL_DAYS]
    summer = g[g['month'].isin([6, 7, 8, 9])]
    caveats = ['FWP decides actual restrictions; this only flags the temperature pattern they watch.']
    cover = summer['temp_max_f'].notna().sum()
    if cover < 100:
        caveats.append(f'Only {int(cover)} of 122 June-September days have a temperature reading.')
    value = {'days_at_or_above': int(hot.sum()), 'threshold_f': threshold_f,
             'hottest_f': float(t['temp_max_f'].max()),
             'hottest_date': str(t.loc[t['temp_max_f'].idxmax(), 'date'].date()),
             'runs_of_3_plus_days': [{'from': str(a.date()), 'to': str(b.date()),
                                      'days': (b - a).days + 1} for a, b in long_runs],
             'days_with_temp': int(len(t))}
    return ToolResult('hot_water_days', value,
                      f'Days in {year} with daily max water temp at or above {threshold_f:g} F, and runs '
                      f'of {config.HOOT_OWL_DAYS}+ consecutive days (the pattern Montana FWP watches for '
                      f'hoot-owl restrictions).', f'{label}, {year}', len(t), caveats)


def hot_water_by_year(df, site, threshold_f: float = config.HOOT_OWL_F) -> ToolResult:
    sn, label, err = _site(df, site)
    if err:
        return ToolResult('hot_water_by_year', error=err)
    g = _gauge(df, sn).dropna(subset=['temp_max_f'])
    if g.empty:
        return ToolResult('hot_water_by_year', error=f'{label} has no water temperature data.')
    rows = []
    for y, w in g.groupby('year'):
        rows.append({'year': int(y), 'days_at_or_above': int((w['temp_max_f'] >= threshold_f).sum()),
                     'hottest_f': float(w['temp_max_f'].max()),
                     'summer_days_with_temp': int(w['month'].isin([6, 7, 8, 9]).sum())})
    caveats = [f'Years with few summer readings undercount hot days: '
               f'{[r["year"] for r in rows if r["summer_days_with_temp"] < 100]}']
    return ToolResult('hot_water_by_year', rows,
                      f'Days per calendar year with daily max water temp at or above {threshold_f:g} F.',
                      label, len(g), caveats)


def low_flow_days(df, site, year: int, threshold_cfs: float) -> ToolResult:
    sn, label, err = _site(df, site)
    if err:
        return ToolResult('low_flow_days', error=err)
    g = _gauge(df, sn)
    g = g[(g['year'] == int(year))].dropna(subset=['flow_cfs'])
    if g.empty:
        return ToolResult('low_flow_days', error=f'No flow for {label} in {year}.')
    low = g[g['flow_cfs'] < threshold_cfs]
    value = {'days_below': int(len(low)), 'threshold_cfs': threshold_cfs,
             'first_day_below': str(low['date'].min().date()) if len(low) else None,
             'lowest_cfs': float(g['flow_cfs'].min()),
             'lowest_date': str(g.loc[g['flow_cfs'].idxmin(), 'date'].date())}
    caveats = [] if len(g) >= 360 or int(year) == df['date'].max().year else \
        [f'Only {len(g)} days of flow in {year}.']
    if int(year) == df['date'].max().year:
        caveats.append(f'{year} is not over yet (data through {df["date"].max().date()}).')
    return ToolResult('low_flow_days', value, f'Days in {year} with daily mean flow below {threshold_cfs:g} cfs.',
                      f'{label}, {year}', len(g), caveats)


def compare_gauges(df, sites: list, start=None, end=None) -> ToolResult:
    if not sites or len(sites) < 2:
        return ToolResult('compare_gauges', error='Give at least two gauges to compare.')
    s, e, err = _dates(df, start, end)
    if err:
        return ToolResult('compare_gauges', error=err)
    rows, caveats, used = [], [], 0
    for site in sites:
        r = compare_to_normal(df, site, s, e) if (e - s).days <= 365 else None
        f = flow_stats(df, site, s, e)
        if f.error:
            return ToolResult('compare_gauges', error=f.error)
        rows.append({'gauge': f.scope.split(',')[0], 'mean_cfs': f.value['mean_cfs'],
                     'max_cfs': f.value['max_cfs'], 'min_cfs': f.value['min_cfs'],
                     'pct_of_median': None if (r is None or r.error) else r.value['pct_of_median']})
        caveats += f.caveats + ([] if (r is None or r.error) else r.caveats)
        used += f.rows_used
    caveats.append('Raw cfs depends on river size; compare percent of median across rivers, not cfs.')
    return ToolResult('compare_gauges', rows,
                      'Daily mean flow stats per gauge over the same window, plus percent of the median '
                      'for that window (windows up to one year).', _fmt_window(s, e), used, caveats)


def data_quality_report(df, notes: list | None = None) -> ToolResult:
    rows = []
    for (sn, label), g in df.groupby(['site_no', 'label']):
        span = (g['date'].max() - g['date'].min()).days + 1
        f = g['flow_cfs'].notna()
        rows.append({
            'gauge': label, 'first': str(g['date'].min().date()), 'last': str(g['date'].max().date()),
            'missing_flow_days': int(span - f.sum()),
            'unreviewed_pct': round(float((g.loc[f, 'flow_status'] == 'Provisional').mean() * 100), 1),
            'estimated_days': int(g.loc[f, 'flow_flags'].str.contains('Estimated').sum()),
            'ice_days': int(g['flow_flags'].str.contains('Ice').sum()),
            'temp_days': int(g['temp_max_c'].notna().sum()),
        })
    value = {'gauges': rows, 'load_notes': [n['message'] for n in (notes or [])]}
    return ToolResult('data_quality_report', value,
                      'Per gauge: missing flow days between its first and last date, share of flow '
                      'values USGS has not reviewed yet, days USGS estimated, ice-affected days, days with '
                      'water temperature.', 'All gauges', len(df))


def flow_change(df, as_of: str | None = None, window_days: int = 7, sites: list | None = None) -> ToolResult:
    """Percent change in daily mean flow at each gauge over `window_days` ending on `as_of`.
    End value = latest flow on or before as_of (no more than 3 days old). Start value = flow
    on the end date minus window_days (or the nearest day up to 2 days either side)."""
    if int(window_days) < 1 or int(window_days) > 365:
        return ToolResult('flow_change', error='Window must be 1 to 365 days.')
    end_cap = pd.Timestamp(as_of) if as_of else df['date'].max()
    if end_cap < df['date'].min() or end_cap > df['date'].max() + pd.Timedelta(days=3):
        return ToolResult('flow_change', error=f'No data for {end_cap.date()}. Loaded data runs '
                          f'{df["date"].min().date()} to {df["date"].max().date()}.')
    site_nos = []
    for s in (sites or list(_groups(df))):
        sn, _, err = _site(df, s)
        if err:
            return ToolResult('flow_change', error=err)
        site_nos.append(sn)
    rows, missing, used = [], [], 0
    for sn in site_nos:
        full = _gauge(df, sn)
        g = full[full['flow_cfs'].notna()]
        e = g[(g['date'] <= end_cap) & (g['date'] > end_cap - pd.Timedelta(days=4))]
        label = full['label'].iloc[0]
        if e.empty:
            missing.append(label)
            continue
        end = e.iloc[-1]
        target = end['date'] - pd.Timedelta(days=int(window_days))
        # Start must be before the end, or a gap in a short window compares a day with itself
        near = g[((g['date'] - target).abs() <= pd.Timedelta(days=2)) & (g['date'] < end['date'])]
        if near.empty:
            missing.append(label)
            continue
        start = near.iloc[(near['date'] - target).abs().argsort().iloc[0]]
        # Under 1 cfs a percent change is noise (0.3 -> 0.2 cfs reads as -33%), so leave it blank
        pct = None if start['flow_cfs'] < MIN_CHANGE_CFS else float((end['flow_cfs'] / start['flow_cfs'] - 1) * 100)
        norms = daily_normals(full, end['water_year'])
        md = '02-28' if end['md'] == '02-29' else end['md']
        med = float(norms.loc[md, 'median']) if md in norms.index else None
        rows.append({'site_no': sn, 'gauge': label, 'river': end['river'],
                     'start_date': str(start['date'].date()), 'start_cfs': float(start['flow_cfs']),
                     'end_date': str(end['date'].date()), 'end_cfs': float(end['flow_cfs']),
                     'change_cfs': float(end['flow_cfs'] - start['flow_cfs']), 'change_pct': pct,
                     'pct_of_median': None if (med is None or med < MIN_CHANGE_CFS)
                     else float(end['flow_cfs'] / med * 100),
                     'status': end['flow_status']})
        used += 2
    caveats = []
    if missing:
        caveats.append('No flow near those dates at: ' + ', '.join(missing))
    if any(r['change_pct'] is None for r in rows):
        caveats.append(f'Percent change is left blank where flow started under {MIN_CHANGE_CFS:g} cfs.')
    if any(r['pct_of_median'] is None for r in rows):
        caveats.append(f'Percent of normal is left blank where normal flow is under {MIN_CHANGE_CFS:g} cfs '
                       f'or there are no other years yet.')
    caveats.append('Dam-controlled reaches (below Hebgen, Ennis, Clark Canyon, Lima, Ruby reservoirs) '
                   'change when releases change, not just with weather.')
    return ToolResult('flow_change', rows,
                      f'Percent change in daily mean flow over {int(window_days)} days, ending on or just '
                      f'before {end_cap.date()}. Percent of median uses the end date.',
                      f'{len(rows)} gauges, {int(window_days)}-day change to {end_cap.date()}', used, caveats)
