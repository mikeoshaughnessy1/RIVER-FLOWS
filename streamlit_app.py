"""Montana River Report: layout only. Data loading lives in data_prep, math in analytics,
the assistant in agent, looks in theme."""
from __future__ import annotations
import hashlib
import io
import math
import pathlib
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import agent
import analytics as A
import config
import data_prep as dp
import theme as T
import usgs

ROOT = pathlib.Path(__file__).parent
st.set_page_config(page_title='Montana River Report', page_icon='🎣', layout='wide')
T.inject()


# ---------------- data ----------------

@st.cache_data(show_spinner=False)
def build_cached(daily_bytes: bytes, sites_bytes: bytes):
    # Keyed on file CONTENTS, so changed data never shows old numbers.
    return dp.build(dp.read_csv(daily_bytes), dp.read_csv(sites_bytes))


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_recent(days: int, api_key: str | None, _salt: str):
    start = (pd.Timestamp.today() - pd.Timedelta(days=days)).date().isoformat()
    return usgs.fetch_daily(list(config.SITES), start, None, api_key)


@st.cache_data(show_spinner=False)
def load_reaches():
    import json
    p = ROOT / 'data' / 'reaches.geojson'
    return json.loads(p.read_text()) if p.exists() else {'features': []}


def secret(name):
    try:
        return st.secrets.get(name)
    except Exception:
        return None


ss = st.session_state
if 'daily_bytes' not in ss:
    ss.daily_bytes = (ROOT / 'data' / 'daily_values.csv.gz').read_bytes()
    ss.sites_bytes = (ROOT / 'data' / 'sites.csv').read_bytes()
    ss.daily_src = 'Snapshot in data/daily_values.csv.gz'
    ss.sites_src = 'data/sites.csv'
    ss.answers, ss.asked = [], 0

# ---------------- sidebar ----------------

with st.sidebar:
    st.markdown('<div class="rr-serif" style="font-size:1.35rem;font-weight:650">River Report</div>'
                '<div style="color:#6b7375;font-size:.8rem;margin-bottom:.8rem">Montana & Yellowstone · USGS gauges</div>',
                unsafe_allow_html=True)
    page = st.radio('Section', ['1  Map', '2  Today', '3  History', '4  Water temp', '5  Ask', '6  Data'],
                    key='page', label_visibility='collapsed')
    region = st.selectbox('Region', ['All Montana'] + config.REGIONS, key='region',
                          help='Filters the gauge lists and centers the map. Ask always sees every gauge.')

try:
    df, sites, notes = build_cached(ss.daily_bytes, ss.sites_bytes)
except ValueError as e:
    T.masthead('Montana River Report', 'The data could not be loaded', str(e))
    T.note('Upload a corrected file on the Data page, or restore the original data.')
    if st.button('Restore original data'):
        for k in ('daily_bytes', 'sites_bytes'):
            ss.pop(k, None)
        st.rerun()
    st.stop()

LAST = df['date'].max()
DATA_KEY = hashlib.md5(ss.daily_bytes[:4096] + ss.daily_bytes[-4096:] + str(len(ss.daily_bytes)).encode()
                       + ss.sites_bytes).hexdigest()
labels = sites.set_index('site_no')['label'].to_dict()
labels = {s: labels.get(s, s) for s in df['site_no'].cat.categories if s in set(df['site_no'].unique())}
reg_of = sites.set_index('site_no')['region'].to_dict()
order_all = [s for s in sites['site_no'] if s in labels] + sorted(s for s in labels if s not in set(sites['site_no']))
order = [s for s in order_all if region == 'All Montana' or reg_of.get(s) == region]
recent_temp = set(df.loc[(df['year'] >= LAST.year - 1) & df['temp_max_c'].notna(), 'site_no'].unique())
with_temp = [s for s in order if s in recent_temp]


@st.cache_data(show_spinner='Crunching flows', max_entries=64)
def change_cached(key, as_of, window):
    return A.flow_change(df, as_of, window)


@st.cache_data(show_spinner='Crunching flows', max_entries=8)
def conditions_cached(key, site_tuple):
    return A.current_conditions(df, list(site_tuple))


@st.cache_data(show_spinner='Preparing the download', max_entries=4)
def region_csv(key, region):
    keep = df if region == 'All Montana' else df[df['site_no'].isin(order)]
    return keep[config.DAILY_COLUMNS].to_csv(index=False)


def pick_default(options, preferred='06043500'):
    return options.index(preferred) if preferred in options else 0
warns = [n for n in notes if n['level'] == 'warn']

with st.sidebar:
    st.markdown('---')
    st.caption(f'Daily data through **{LAST:%b %d, %Y}**')
    st.caption(f'Source: {ss.daily_src}')
    if warns:
        st.caption(f'⚠ {len(warns)} data note(s) on the Data page')

# ---------------- helpers ----------------


def hydrograph(site, wy, height=330):
    g = A._gauge(df, site)
    norms = A.daily_normals(g, wy)
    days = pd.date_range(f'{wy - 1}-10-01', f'{wy}-09-30')
    md = days.strftime('%m-%d').str.replace('02-29', '02-28')
    n = norms.reindex(md)
    cur = g[g['water_year'] == wy].set_index('date')['flow_cfs']
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=days, y=n['p90'], line=dict(width=0), hoverinfo='skip', showlegend=False))
    fig.add_trace(go.Scatter(x=days, y=n['p10'], fill='tonexty', fillcolor='rgba(214,227,223,.55)',
                             line=dict(width=0), name='10th to 90th pct', hoverinfo='skip'))
    fig.add_trace(go.Scatter(x=days, y=n['p75'], line=dict(width=0), hoverinfo='skip', showlegend=False))
    fig.add_trace(go.Scatter(x=days, y=n['p25'], fill='tonexty', fillcolor='rgba(143,181,179,.45)',
                             line=dict(width=0), name='25th to 75th', hoverinfo='skip'))
    fig.add_trace(go.Scatter(x=days, y=n['median'], line=dict(color=T.MUTED, width=1, dash='dot'),
                             name='Median', hovertemplate='%{y:,.0f} cfs median<extra></extra>'))
    fig.add_trace(go.Scatter(x=cur.index, y=cur.values, line=dict(color=T.RIVER, width=2.2),
                             name=f'Water year {wy}', hovertemplate='%{x|%b %d}: %{y:,.0f} cfs<extra></extra>'))
    fig.update_layout(height=height, yaxis_title='cfs', hovermode='x unified')
    fig.update_xaxes(tickformat='%b')
    return fig


def pct_label(p):
    if p is None:
        return '<span class="rr-pill warn">no normal</span>'
    cls = 'hot' if p < 75 else ('warn' if p > 130 else '')
    return f'<span class="rr-pill {cls}">{p:,.0f}%</span>'


# ---------------- 1 Map ----------------

if page.endswith('Map'):
    where = 'Montana and Yellowstone' if region == 'All Montana' else region
    T.masthead(where, 'Which rivers are rising and dropping',
               'Each river is colored by the gauge just below it. Red is dropping, blue is rising. '
               'Pick any date and window to see the change at that moment.')
    c1, c2, c3 = st.columns([1.2, 1.4, 1.4])
    mode = c1.radio('Color by', ['Change', 'Vs normal'], horizontal=True, key='map_mode',
                    help='Change: percent change over the window. Vs normal: flow on the end date as a '
                         'percent of the median for that calendar day.')
    window = c2.select_slider('Window', [1, 3, 7, 14, 30], value=7, key='map_window',
                              format_func=lambda d: f'{d} day' + ('s' if d > 1 else ''),
                              disabled=mode != 'Change')
    as_of = c3.date_input('As of', LAST, min_value=df['date'].min() + pd.Timedelta(days=31),
                          max_value=LAST, key='map_date')
    fc = change_cached(DATA_KEY, str(as_of), window)
    if fc.error:
        T.note(fc.error)
        st.stop()
    rows = {r['site_no']: r for r in fc.value}

    def metric(r):
        return r['change_pct'] if mode == 'Change' else r['pct_of_median']

    def to_t(v):
        # Change: -50% .. +50% maps to red .. blue. Vs normal: 50% .. 200% on a log scale.
        if v is None:
            return None
        if mode == 'Change':
            return (max(-50, min(50, v)) + 50) / 100
        return (max(-1, min(1, math.log2(max(v, 1) / 100))) + 1) / 2

    def color_of(sn):
        r = rows.get(sn)
        v = metric(r) if r else None
        return None if v is None else round(to_t(v) * 20) / 20     # 21 color steps

    mean_flow = A._groups(df)
    mean_flow = {k: (float(m) if pd.notna(m := g['flow_cfs'].mean()) else 0.0) for k, g in mean_flow.items()}
    # Draw "below the gauge" stretches first (small rivers first so a big river's color wins
    # below a confluence), then each gauge's own reach with big rivers first and small on top.
    # Lines that share a color and width go in one trace so the map stays quick with 200 gauges.
    feats = [f for f in load_reaches()['features'] if f['properties']['site_no'] in labels]
    feats.sort(key=lambda f: (not f['properties'].get('below', False),
                              mean_flow.get(f['properties']['site_no'], 0) * (1 if f['properties'].get('below') else -1)))
    fig = go.Figure()
    batch_key, lon, lat = None, [], []

    def flush():
        if lon:
            t, w = batch_key
            fig.add_trace(go.Scattermap(lon=lon, lat=lat, mode='lines', hoverinfo='skip', showlegend=False,
                                        line=dict(color=T.OFF_SEASON if t is None else T.diverging_color(t), width=w)))

    for f in feats:
        sn = f['properties']['site_no']
        w = round(1.2 + 0.9 * math.log10(max(mean_flow.get(sn, 10), 10)), 1)
        k = (color_of(sn), w)
        if k != batch_key:
            flush()
            batch_key, lon, lat = k, [], []
        for line in f['geometry']['coordinates']:
            lon += [p[0] for p in line] + [None]
            lat += [p[1] for p in line] + [None]
    flush()

    site_xy = sites.set_index('site_no')
    mk = [s for s in order_all if s in site_xy.index]
    vals = [metric(rows[s]) if s in rows else None for s in mk]

    def tip(s, v):
        r = rows.get(s)
        if r is None:
            return f'{labels[s]}<br>no recent flow (seasonal or off)'
        if mode == 'Change':
            ch = 'n/a' if r['change_pct'] is None else f"{r['change_pct']:+.0f}%"
            return (f"<b>{labels[s]}</b><br>{r['start_cfs']:,.0f} to {r['end_cfs']:,.0f} cfs ({ch})"
                    f"<br>{r['start_date']} to {r['end_date']}")
        pm = 'no normal yet' if r['pct_of_median'] is None else f"{r['pct_of_median']:.0f}% of normal"
        return f"<b>{labels[s]}</b><br>{r['end_cfs']:,.0f} cfs on {r['end_date']}<br>{pm}"
    fig.add_trace(go.Scattermap(lon=site_xy.loc[mk, 'lon'], lat=site_xy.loc[mk, 'lat'], mode='markers',
                                marker=dict(size=10, color='white'), hoverinfo='skip', showlegend=False))
    fig.add_trace(go.Scattermap(
        lon=site_xy.loc[mk, 'lon'], lat=site_xy.loc[mk, 'lat'], mode='markers',
        marker=dict(size=7, color=[T.OFF_SEASON if v is None else T.diverging_color(to_t(v)) for v in vals]),
        text=[tip(s, v) for s, v in zip(mk, vals)], hoverinfo='text', showlegend=False))
    scale = [[t, c] for t, c in T.DIVERGING]
    if mode == 'Change':
        cb = dict(title=dict(text='% change', side='right'), tickvals=[0, .25, .5, .75, 1],
                  ticktext=['-50%+', '-25%', '0', '+25%', '+50%+'])
    else:
        cb = dict(title=dict(text='vs normal', side='right'), tickvals=[0, .25, .5, .75, 1],
                  ticktext=['50% or less', '71%', '100%', '141%', '200%+'])
    cb.update(thickness=12, len=.6, x=1.0, y=.5, outlinewidth=0, tickfont=dict(size=11))
    fig.add_trace(go.Scattermap(lon=[-110.0], lat=[47.0], mode='markers', hoverinfo='skip', showlegend=False,
                                marker=dict(size=0.1, color=[0.5], colorscale=scale, cmin=0, cmax=1,
                                            showscale=True, colorbar=cb)))
    clat, clon, zoom = config.REGION_VIEW.get(region, config.REGION_VIEW['All Montana'])
    fig.update_layout(map=dict(style='carto-positron', center=dict(lat=clat, lon=clon), zoom=zoom),
                      height=640, margin=dict(l=0, r=0, t=0, b=0))
    st.plotly_chart(fig, width='stretch', config={'displayModeBar': False, 'scrollZoom': True})
    st.caption('Scroll or pinch to zoom. Hover a gauge dot for its numbers.')

    in_view = set(order)
    live = [r for r in fc.value if r['site_no'] in in_view and metric(r) is not None]
    if live:
        lo = min(live, key=metric)
        hi = max(live, key=metric)
        fmt = (lambda v: f'{v:+.0f}%') if mode == 'Change' else (lambda v: f'{v:.0f}%')
        if mode == 'Change':
            k1 = ('Rising 5%+', sum(1 for r in live if r['change_pct'] >= 5))
            k2 = ('Dropping 5%+', sum(1 for r in live if r['change_pct'] <= -5))
        else:
            k1 = ('Above normal', sum(1 for r in live if r['pct_of_median'] >= 110))
            k2 = ('Below normal', sum(1 for r in live if r['pct_of_median'] <= 90))
        T.stats([(k1[0], str(k1[1]), f'of {len(live)} gauges'), (k2[0], str(k2[1]), f'of {len(live)} gauges'),
                 ('Biggest drop' if mode == 'Change' else 'Lowest', fmt(metric(lo)), lo['gauge']),
                 ('Biggest rise' if mode == 'Change' else 'Highest', fmt(metric(hi)), hi['gauge'])])

    T.figure(1, 'Every gauge, ranked',
             f"{'Change over ' + str(window) + ' days' if mode == 'Change' else 'Percent of normal'} "
             f'ending {pd.Timestamp(as_of):%b %d, %Y}, {where}.')
    ranked = sorted((r for r in fc.value if r['site_no'] in in_view),
                    key=lambda r: (metric(r) is None, metric(r) or 0))
    show_all = st.toggle('Show every gauge', value=len(ranked) <= 30, key='map_all')
    shown = ranked if show_all else ranked[:10] + ranked[-10:]
    trows = []
    for r in shown:
        v = metric(r)
        sw = T.OFF_SEASON if v is None else T.diverging_color(to_t(v))
        trows.append({'sw_html': f'<span style="display:inline-block;width:22px;height:4px;border-radius:2px;'
                                 f'background:{sw};vertical-align:middle"></span>',
                      'gauge': r['gauge'], 'river': r['river'],
                      'start': f"{r['start_cfs']:,.0f}", 'end': f"{r['end_cfs']:,.0f}",
                      'chg': '-' if r['change_pct'] is None else f"{r['change_pct']:+.0f}%",
                      'norm': '-' if r['pct_of_median'] is None else f"{r['pct_of_median']:.0f}%"})
    if not show_all and len(ranked) > 20:
        st.caption(f'Showing the 10 biggest drops and 10 biggest rises of {len(ranked)}.')
    T.table(trows, [('sw_html', ''), ('gauge', 'Gauge'), ('river', 'River'), ('start', 'Start cfs'),
                    ('end', 'End cfs'), ('chg', 'Change'), ('norm', 'Vs normal')],
            num=('start', 'end', 'chg', 'norm'))
    off = [labels[s] for s in order if s not in rows]
    if off:
        st.caption(f'{len(off)} gauge(s) had no flow near this date (seasonal gauges shut off in fall): '
                   + ', '.join(off[:15]) + ('…' if len(off) > 15 else '') + '.')
    st.caption(fc.caveats[-1])

# ---------------- 2 Today ----------------

elif page.endswith('Today'):
    cc = conditions_cached(DATA_KEY, tuple(order))
    rows = cc.value
    where = 'Montana and Yellowstone' if region == 'All Montana' else region
    T.masthead('Montana River Report', f'Rivers on {LAST:%A, %B %-d}',
               f'{len(rows)} USGS gauges with recent flow, {where}. '
               'Flows are daily means; "normal" is the median for the same day across the gauge\'s record.')
    if not rows:
        T.note('No gauges in this region have recent flow.')
        st.stop()
    near = [r for r in rows if r['pct_of_median'] is not None] or rows
    hi = max(near, key=lambda r: r['pct_of_median'] or 0)
    lo = min(near, key=lambda r: r['pct_of_median'] or 0)
    temps = [r for r in rows if r['water_temp_max_f'] is not None]
    warm = max(temps, key=lambda r: r['water_temp_max_f']) if temps else None
    gg = next((r for r in rows if r['site_no'] == '06043500'), max(rows, key=lambda r: r['flow_cfs']))
    pm = lambda r: '–' if r['pct_of_median'] is None else f"{r['pct_of_median']:.0f}%"
    T.stats([
        (gg['gauge'][:24], f"{gg['flow_cfs']:,.0f} cfs",
         f"{gg['pct_of_median']:.0f}% of normal" if gg['pct_of_median'] else ''),
        ('Highest vs normal', pm(hi), hi['gauge']),
        ('Lowest vs normal', pm(lo), lo['gauge']),
        ('Warmest water', f"{warm['water_temp_max_f']:.0f}°F" if warm else '–', warm['gauge'] if warm else 'no sensors'),
    ])

    T.figure(2, 'Every gauge, today', 'Percent of median: under 75% is low for the date, over 130% is high.')
    trows, group = [], None
    group_by = 'river' if region != 'All Montana' else 'region'
    pos = {s: i for i, s in enumerate(order)}
    for r in sorted(rows, key=lambda r: pos.get(r['site_no'], 1e9)):
        g = r['river'] if group_by == 'river' else reg_of.get(r['site_no'], 'Other')
        if g != group:
            group = g
            trows.append({'_group': g})
        ch = r['change_7d_pct']
        flags = ' '.join(x for x in [r['status'] == 'Provisional' and 'provisional', r['flags']] if x)
        trows.append({'gauge': r['gauge'], 'flow': T.cfs(r['flow_cfs']), 'median': T.cfs(r['median_cfs']),
                      'pct_html': pct_label(r['pct_of_median']),
                      'chg': '–' if ch is None else f'{ch:+.0f}%',
                      'temp': '–' if r['water_temp_max_f'] is None else f"{r['water_temp_max_f']:.0f}°F",
                      'date': pd.Timestamp(r['date']).strftime('%b %d'), 'flags': flags})
    T.table(trows, [('gauge', 'Gauge'), ('flow', 'Flow cfs'), ('median', 'Normal'), ('pct_html', 'vs normal'),
                    ('chg', '7-day'), ('temp', 'Water max'), ('date', 'Date'), ('flags', 'Notes')],
            num=('flow', 'median', 'chg', 'temp'))
    if cc.caveats:
        stale = [c for c in cc.caveats if 'Not current' in c or 'shaky' in c]
        for c in stale:
            st.caption(c)

    T.figure(3, 'This water year against the record')
    pick = st.selectbox('Gauge', order, index=pick_default(order), format_func=labels.get, key='today_gauge')
    wy = int(A._gauge(df, pick)['water_year'].max())
    if LAST.month == 10 or (LAST.month == 11 and LAST.day < 20):
        # Early in a water year there's only a few weeks of the new one, so open on the year just finished
        wy_show = st.radio('Water year', [wy - 1, wy], horizontal=True, key='today_wy',
                           format_func=lambda y: f'{y} (Oct {y - 1} to Sep {y})')
    else:
        wy_show = wy
    st.plotly_chart(hydrograph(pick, wy_show), width='stretch', config={'displayModeBar': False})
    st.markdown('<div class="rr-cap">Bands show where flows usually sit on each date in every other water '
                'year at this gauge. Dotted line is the median.</div>', unsafe_allow_html=True)

# ---------------- 2 History ----------------

elif page.endswith('History'):
    T.masthead('History', 'Runoff, peaks and the long view',
               'Peak timing, monthly patterns and any window compared with every earlier year.')
    pick = st.selectbox('Gauge', order, index=pick_default(order), format_func=labels.get, key='hist_gauge')
    pk = A.annual_peaks(df, pick)
    tr = A.runoff_timing_trend(df, pick)
    p = pd.DataFrame(pk.value)
    full = p[p['days_with_data'] >= A.FULL_YEAR_DAYS]
    big = full.loc[full['peak_cfs'].idxmax()] if len(full) else None
    T.stats([
        ('Years of record', f'{len(full)}', f"full water years since {int(p['water_year'].min())}"),
        ('Median peak date', tr.value['median_peak_date'] if not tr.error else '–', 'daily mean peak'),
        ('Biggest peak', T.cfs(big['peak_cfs']) + ' cfs' if big is not None else '–',
         pd.Timestamp(big['peak_date']).strftime('%b %d, %Y') if big is not None else ''),
        ('Timing trend', f"{tr.value['days_per_decade']:+.1f} d/decade" if not tr.error else '–',
         f"R² {tr.value['r_squared']:.2f}, mostly noise" if not tr.error and tr.value['r_squared'] < .2 else
         (f"R² {tr.value['r_squared']:.2f}" if not tr.error else tr.error[:40])),
    ])
    if 'Madison' in labels[pick]:
        st.caption('The Madison is dam-regulated (Hebgen and Ennis), so its runoff is partly managed.')

    T.figure(4, 'When the river peaked each year', 'Dot size is the peak flow. Earlier dots = earlier runoff.')
    pf = full.copy()
    pf['day'] = pd.to_datetime('2001-01-01') + pd.to_timedelta(pf['peak_day_of_year'] - 1, unit='D')
    fig = go.Figure(go.Scatter(
        x=pf['water_year'], y=pf['day'], mode='markers',
        marker=dict(size=(pf['peak_cfs'] / pf['peak_cfs'].max() * 26 + 6), color=T.RIVER, opacity=.75,
                    line=dict(color=T.PAPER, width=1)),
        customdata=pf[['peak_cfs', 'peak_date']], hovertemplate='WY %{x}: %{customdata[0]:,.0f} cfs on %{customdata[1]}<extra></extra>'))
    fig.update_layout(height=320, yaxis=dict(tickformat='%b %d', title='Peak date'))
    st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})

    c1, c2 = st.columns([1, 1], gap='large')
    with c1:
        T.figure(5, 'Typical flow by month')
        m = pd.DataFrame(A.monthly_flow(df, pick).value)
        mo = ['Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep']
        m = m.set_index('month').reindex(mo).reset_index()
        fig = go.Figure(go.Bar(x=m['month'], y=m['median_cfs'], marker_color=T.RIVER_LIGHT,
                               text=m['median_cfs'].map(lambda v: f'{v:,.0f}'), textposition='outside',
                               hovertemplate='%{x}: %{y:,.0f} cfs median<extra></extra>'))
        fig.update_layout(height=300, yaxis_title='Median cfs')
        st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
    with c2:
        T.figure(6, 'Any window vs every earlier year')
        g = A._gauge(df, pick)
        d0 = st.date_input('Window', (LAST - pd.Timedelta(days=29), LAST), min_value=g['date'].min(),
                           max_value=LAST, key='hist_win')
        if isinstance(d0, tuple) and len(d0) == 2:
            r = A.compare_to_normal(df, pick, str(d0[0]), str(d0[1]))
            if r.error:
                T.note(r.error)
            else:
                v = r.value
                T.stats([('Window mean', T.cfs(v['window_mean_cfs']), 'cfs'),
                         ('Normal', T.cfs(v['median_of_other_years_cfs']), 'cfs median'),
                         ('Percent', f"{v['pct_of_median']:.0f}%", 'of normal'),
                         ('Rank', v['rank'].split(' (')[0], '1 = wettest')])
                for c in r.caveats:
                    st.caption(c)

# ---------------- 3 Water temp ----------------

elif page.endswith('Water temp'):
    T.masthead('Water temperature', 'Hot water and the 73°F line',
               'Montana FWP watches for daily max water temps at or above 73°F three days running when '
               'deciding hoot-owl restrictions. This page shows that pattern; FWP makes the call.')
    if not with_temp:
        T.note('None of the loaded gauges has recent water temperature data.')
        st.stop()
    pick = st.selectbox('Gauge (only gauges with a recent temperature sensor)', with_temp,
                        index=pick_default(with_temp, '06052500'),
                        format_func=labels.get, key='temp_gauge')
    by = A.hot_water_by_year(df, pick)
    yrs = pd.DataFrame(by.value)
    yrs = yrs[yrs['summer_days_with_temp'] >= 60]
    T.figure(7, 'Days at or above 73°F, by year', 'Years with fewer than 60 summer readings are left out.')
    fig = go.Figure(go.Bar(x=yrs['year'], y=yrs['days_at_or_above'],
                           marker_color=[T.HOT if d > 0 else T.RULE for d in yrs['days_at_or_above']],
                           text=yrs['days_at_or_above'], textposition='outside',
                           hovertemplate='%{x}: %{y} days, hottest %{customdata:.1f}°F<extra></extra>',
                           customdata=yrs['hottest_f']))
    fig.update_layout(height=280, yaxis_title='Days', xaxis=dict(dtick=1, tickangle=-45))
    st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})

    year = st.select_slider('Year', options=sorted(yrs['year'].tolist()), value=int(yrs['year'].max()), key='temp_year')
    hw = A.hot_water_days(df, pick, year)
    if hw.error:
        T.note(hw.error)
    else:
        v = hw.value
        T.stats([('Days ≥ 73°F', str(v['days_at_or_above']), f'{year}'),
                 ('Hottest', f"{v['hottest_f']:.1f}°F", pd.Timestamp(v['hottest_date']).strftime('%b %d')),
                 ('3+ day runs', str(len(v['runs_of_3_plus_days'])), 'consecutive hot days'),
                 ('Readings', str(v['days_with_temp']), 'days with a temp')])
        T.figure(8, f'Daily water temperature, {year}')
        g = A._gauge(df, pick)
        g = g[g['year'] == year]
        fig = go.Figure()
        for a in v['runs_of_3_plus_days']:
            fig.add_vrect(x0=a['from'], x1=pd.Timestamp(a['to']) + pd.Timedelta(days=1),
                          fillcolor='#f3dfd3', line_width=0, layer='below')
        fig.add_trace(go.Scatter(x=g['date'], y=g['temp_mean_f'], name='Daily mean',
                                 line=dict(color=T.RIVER_LIGHT, width=1.4)))
        fig.add_trace(go.Scatter(x=g['date'], y=g['temp_max_f'], name='Daily max',
                                 line=dict(color=T.HOT, width=1.8)))
        fig.add_hline(y=config.HOOT_OWL_F, line=dict(color=T.INK, width=1, dash='dash'),
                      annotation_text='73°F', annotation_position='top left')
        fig.update_layout(height=320, yaxis_title='°F', hovermode='x unified')
        st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
        st.caption('Shaded spans are runs of 3+ days at or above 73°F. ' + ' '.join(hw.caveats[1:]))

# ---------------- 4 Ask ----------------

elif page.endswith('Ask'):
    T.masthead('Ask', 'Questions about the rivers',
               'Every number comes from a calculation on the loaded data. The method under each answer '
               'shows exactly which tool ran.')
    key = secret('GEMINI_API_KEY')
    models = tuple(m for m in [secret('GEMINI_MODEL'), 'gemini-3-flash-preview', 'gemini-2.5-flash'] if m)
    st.caption(('Gemini is on.' if key else 'No Gemini key set, so a keyword router answers.')
               + f' {config.QUESTION_LIMIT - ss.asked} questions left this session.')
    ex = ['How is the Gallatin running?', 'How did July 2026 compare to normal at Logan?',
          'Hot water days at Logan in 2021', 'Is runoff coming earlier on the Yellowstone?',
          'How many days was the Jefferson below 500 cfs in 2025?', 'Is the data clean?']
    cols = st.columns(3)
    for i, q in enumerate(ex):
        if cols[i % 3].button(q, key=f'ex{i}', width='stretch'):
            ss.pending = q
    q = st.chat_input('Ask about flows, runoff, water temps…') or ss.pop('pending', None)
    if q:
        if ss.asked >= config.QUESTION_LIMIT:
            T.note('Question limit reached for this session. Reload the page to reset.')
        else:
            ss.asked += 1
            with st.spinner('Running the numbers'):
                ss.answers.insert(0, agent.answer_question(q, df, key, models, notes))
    for a in ss.answers:
        st.markdown(f'<div class="rr-entry"><div class="q">{T.esc(a["question"])}</div>'
                    f'<div style="color:#6b7375;font-size:.8rem">Scope: {T.esc(a["scope"])} · {T.esc(a["mode"])}</div>'
                    '</div>', unsafe_allow_html=True)
        for f in a['flags']:
            T.note(f)
        st.markdown('<div class="rr-entry" style="border:none;padding:0"><div class="lab">Findings</div></div>',
                    unsafe_allow_html=True)
        st.markdown(a['findings'].replace('$', r'\$').replace('\n', '  \n'))
        if a.get('interpretation'):
            st.markdown('<div class="rr-entry" style="border:none;padding:0"><div class="lab">Interpretation</div></div>',
                        unsafe_allow_html=True)
            st.markdown(a['interpretation'].replace('$', r'\$'))
        if a.get('caveats'):
            st.caption('Caveats: ' + ' '.join(a['caveats']).replace('$', r'\$'))
        if a.get('next_steps'):
            st.caption('Next: ' + a['next_steps'].replace('$', r'\$'))
        with st.expander('Method (tool calls)'):
            for e in a['tool_log']:
                st.code(f"{e['tool']}({e['args']})", language='python')
                r = e['result']
                st.json({k: r[k] for k in ('definition', 'scope', 'rows_used', 'caveats', 'error')}, expanded=False)
                if isinstance(r['value'], list) and r['value'] and isinstance(r['value'][0], dict):
                    st.dataframe(pd.DataFrame(r['value']), hide_index=True, width='stretch')
                elif r['value'] is not None:
                    st.json(r['value'], expanded=False)

# ---------------- 5 Data ----------------

else:
    T.masthead('Data', 'Where the numbers come from',
               f'USGS daily values (provisional and approved) for {df["site_no"].nunique()} gauges, water year 2001 to now.')
    T.stats([('Daily rows', f'{len(df):,}', 'one per gauge per day'),
             ('Gauges', str(df['site_no'].nunique()), f"{len(with_temp)} with water temp"),
             ('First day', f"{df['date'].min():%b %Y}", ''), ('Last day', f'{LAST:%b %d, %Y}', 'refreshed' if 'refresh' in ss.daily_src else ('uploaded' if 'Uploaded' in ss.daily_src else 'snapshot'))])

    T.figure(9, 'Get the latest from USGS',
             f'Pulls the last {config.REFRESH_DAYS} days from the USGS Water Data API and lays it over the '
             'snapshot (recent provisional values get revised).')
    c1, c2 = st.columns([1, 2])
    if c1.button('Refresh from USGS', type='primary'):
        try:
            with st.spinner('Asking USGS'):
                fresh = fetch_recent(config.REFRESH_DAYS, secret('USGS_API_KEY'), str(pd.Timestamp.now().floor('h')))
            merged = dp.merge_refresh(dp.read_csv(ss.daily_bytes), fresh)
            buf = io.StringIO()
            merged.to_csv(buf, index=False)
            ss.daily_bytes = buf.getvalue().encode()
            ss.daily_src = f'Snapshot + USGS refresh {pd.Timestamp.now(tz="America/Denver"):%b %d %H:%M}'
            st.toast(f'Got {len(fresh):,} recent rows from USGS.')
            st.rerun()
        except Exception as e:
            T.note(f'USGS refresh failed: {e}. The app keeps using the data it has.')
    c2.caption('Without a USGS API key, USGS allows only a few requests per hour. A free key goes in '
               'the app secrets as USGS_API_KEY.')

    T.figure(10, 'Upload changed data', 'Replaces just that table. Use this for the validation tests.')
    up = st.file_uploader('Daily values or sites CSV', type=['csv'], key='upload')
    if up is not None:
        h = hashlib.md5(up.getvalue()).hexdigest()
        if ss.get('last_upload') != h:
            name = up.name.lower()
            if any(k in name for k in config.FILES['sites']):
                ss.sites_bytes, ss.sites_src = up.getvalue(), f'Uploaded {up.name}'
            elif any(k in name for k in config.FILES['daily']):
                ss.daily_bytes, ss.daily_src = up.getvalue(), f'Uploaded {up.name}'
            else:
                T.note('File name must contain "daily" or "sites" so the app knows which table it replaces.')
                st.stop()
            ss.last_upload = h
            st.rerun()
    if st.button('Restore original data'):
        ss.daily_bytes = (ROOT / 'data' / 'daily_values.csv.gz').read_bytes()
        ss.sites_bytes = (ROOT / 'data' / 'sites.csv').read_bytes()
        ss.daily_src, ss.sites_src, ss.last_upload = 'Snapshot in data/daily_values.csv.gz', 'data/sites.csv', None
        st.rerun()
    tot = df['flow_cfs'].sum()
    st.caption(f'Check sum: total of all daily flows = {tot:,.0f} cfs-days. Sites from {ss.sites_src}.')

    T.figure(11, 'Load notes')
    for n in notes:
        T.note(n['message'], ok=n['level'] == 'ok')

    T.figure(12, 'Data quality by gauge',
             'Provisional = not yet reviewed by USGS. Estimated days are mostly winter ice.')
    q = A.data_quality_report(df, notes).value['gauges']
    T.table(q, [('gauge', 'Gauge'), ('first', 'First'), ('last', 'Last'), ('missing_flow_days', 'Missing'),
                ('provisional_pct', 'Prov. %'), ('estimated_days', 'Estimated'), ('ice_days', 'Ice'),
                ('temp_days', 'Temp days')],
            num=('missing_flow_days', 'provisional_pct', 'estimated_days', 'ice_days', 'temp_days'))
    st.download_button(f'Download daily data for {region} (CSV)', region_csv(DATA_KEY, region),
                       f"daily_values_{region.lower().replace(' ', '_')}.csv", 'text/csv')

T.colophon('Data: U.S. Geological Survey, National Water Information System, via the USGS Water Data API. '
           'Recent values are provisional. Not a safety tool; check conditions and FWP rules before you go.')
