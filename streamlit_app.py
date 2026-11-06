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
def load_reaches(file_stamp):
    # file_stamp (size, mtime) is part of the cache key, so a new reaches file is never
    # hidden behind a cached old one after a redeploy.
    import json
    p = ROOT / 'data' / 'reaches.geojson'
    return json.loads(p.read_text()) if p.exists() else {'features': []}


def reaches():
    p = ROOT / 'data' / 'reaches.geojson'
    st_ = p.stat() if p.exists() else None
    return load_reaches((st_.st_size, st_.st_mtime) if st_ else None)


def secret(name):
    try:
        return st.secrets.get(name)
    except Exception:
        return None


def snapshot_info():
    import json
    p = ROOT / 'data' / 'snapshot.json'
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return {}


SNAP = snapshot_info()


def snapshot_origin():
    d = SNAP.get('downloaded')
    return f'snapshot downloaded {T.date(d)}' if d else 'bundled snapshot'


ss = st.session_state
if 'daily_bytes' not in ss:
    ss.daily_bytes = (ROOT / 'data' / 'daily_values.csv.gz').read_bytes()
    ss.sites_bytes = (ROOT / 'data' / 'sites.csv').read_bytes()
    ss.daily_src = 'Snapshot in data/daily_values.csv.gz'
    ss.sites_src = 'data/sites.csv'
    ss.data_origin = snapshot_origin()
    ss.answers, ss.asked = [], 0

# Streamlit forgets a widget's value when its page isn't on screen. Re-assigning keeps the
# map date, window, region and gauge picks when you move between sections and come back.
PERSIST = ('region', 'map_mode', 'map_window', 'map_date', 'map_all', 'map_find', 'today_gauge', 'today_wy',
           'hist_gauge', 'hist_win', 'temp_gauge', 'temp_year')
for _k in PERSIST:
    if _k in ss:
        ss[_k] = ss[_k]

# ---------------- sidebar ----------------

with st.sidebar:
    st.markdown('<div class="rr-brand">River Report</div>'
                '<div class="rr-brand-sub">Montana & Yellowstone · USGS gauges</div>', unsafe_allow_html=True)
    page = st.radio('Section', ['1  Map', '2  Today', '3  History', '4  Water temp', '5  Ask', '6  Data'],
                    key='page', label_visibility='collapsed')
    region = st.selectbox('Region', ['All Montana'] + config.REGIONS, key='region',
                          help='Filters the gauge lists and centers the map. Ask always sees every gauge.')

try:
    df, sites, notes = build_cached(ss.daily_bytes, ss.sites_bytes)
except ValueError as e:
    T.masthead('Montana River Report', 'The data could not be loaded',
               'The file that was loaded is missing something the app needs. Nothing below is shown '
               'until the data is fixed, so no numbers are guessed.')
    T.note(str(e), error=True)
    if st.button('Restore the original data', type='primary'):
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
recent_temp = set(df.loc[(df['year'] >= LAST.year - 1) & df['temp_max_c'].notna(), 'site_no'].unique()) \
    - set(config.THERMAL)
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


def default(key, value):
    """Set a widget's starting value once, in session state (not on the widget), so a
    remembered value and a default never fight."""
    if key not in ss:
        ss[key] = value


def keep_valid(key, options):
    """Drop a remembered pick that isn't valid here (e.g. a gauge from another region)."""
    if key in ss and ss[key] not in options:
        del ss[key]


warns = [n for n in notes if n['level'] == 'warn']
TODAY = pd.Timestamp.now(tz='America/Denver').tz_localize(None).normalize()
AGE_DAYS = int((TODAY - LAST).days)
STALE = AGE_DAYS > 3
recent_flow = set(df.loc[(df['date'] > LAST - pd.Timedelta(days=4)) & df['flow_cfs'].notna(), 'site_no'].unique())
WHERE = 'Montana and Yellowstone' if region == 'All Montana' else region


def status_line():
    """Observation date vs how the data got here, on every page."""
    reporting = sum(1 for s in order if s in recent_flow)
    parts = [('Newest reading', f'{T.date(LAST)} daily mean'), ('Data', ss.data_origin),
             f'{reporting} of {len(order)} gauges reporting']
    if warns:
        parts.append(f'{len(warns)} data note{"s" if len(warns) > 1 else ""} on the Data page')
    if STALE:
        parts.append(f'The newest reading is {AGE_DAYS} days old. Refresh it on the Data page.')
    T.status(parts, stale=STALE)


with st.sidebar:
    st.markdown('---')
    st.caption(f'Newest reading **{T.date(LAST)}**  \n{ss.data_origin[:1].upper() + ss.data_origin[1:]}')
    if warns:
        st.caption(f'{len(warns)} data note{"s" if len(warns) > 1 else ""} on the Data page')

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
    fig.update_layout(height=height, yaxis_title='Flow (cfs)', hovermode='x unified')
    fig.update_xaxes(tickformat='%b')
    if cur.empty:
        fig.add_annotation(text='No readings this water year', showarrow=False, xref='paper', yref='paper',
                           x=.5, y=.5, font=dict(color=T.MUTED))
    return fig


def pct_label(p):
    if p is None:
        return '<span class="rr-pill warn">no normal</span>'
    cls = 'hot' if p < 75 else ('warn' if p > 130 else '')
    return f'<span class="rr-pill {cls}">{p:,.0f}%</span>'


# ---------------- 1 Map ----------------

if page.endswith('Map'):
    T.masthead(WHERE, 'Which rivers are rising and dropping',
               'Each river is colored by the gauge just below it. Pick a window and a date to see what '
               'changed, where, and how current the reading is.')
    status_line()
    c1, c2, c3 = st.columns([1.15, 1.45, 1.4], gap='medium')
    mode = c1.radio('Color rivers by', ['Change', 'Vs normal'], horizontal=True, key='map_mode',
                    help='Change: percent change in daily flow over the window. Vs normal: flow on the '
                         'end date as a percent of the median for that calendar day in other years.')
    default('map_window', 7)
    window = c2.select_slider('Change window', [1, 3, 7, 14, 30], key='map_window',
                              format_func=lambda d: f'{d} day' + ('s' if d > 1 else ''),
                              disabled=mode != 'Change',
                              help='Only used when coloring by change.')
    default('map_date', LAST.date())
    if ss['map_date'] > LAST.date():          # data was swapped for an older file
        ss['map_date'] = LAST.date()
    as_of = c3.date_input('As of', min_value=df['date'].min() + pd.Timedelta(days=31),
                          max_value=LAST, key='map_date', format='MM/DD/YYYY',
                          help=f'Any day from {T.date(df["date"].min() + pd.Timedelta(days=31))} '
                               f'to the newest reading, {T.date(LAST)}.')
    fc = change_cached(DATA_KEY, str(as_of), window)
    if fc.error:
        T.note(fc.error, error=True)
        st.stop()
    rows = {r['site_no']: r for r in fc.value}
    end_label = T.date(as_of)
    historical = pd.Timestamp(as_of) < LAST

    def metric(r):
        return r['change_pct'] if mode == 'Change' else r['pct_of_median']

    def to_t(v):
        # Change: -50% .. +50% maps to red .. blue. Vs normal: 50% .. 200% on a log scale.
        if v is None:
            return None
        if mode == 'Change':
            return (max(-50, min(50, v)) + 50) / 100
        return (max(-1, min(1, math.log2(max(v, 1) / 100))) + 1) / 2

    def state(v):
        """Direction word and symbol, so meaning never rests on color alone."""
        if v is None:
            return '○', 'No reading'
        if mode == 'Change':
            return ('▲', 'Rising') if v >= 5 else (('▼', 'Dropping') if v <= -5 else ('●', 'Steady'))
        return ('▲', 'Above normal') if v >= 110 else (('▼', 'Below normal') if v <= 90 else ('●', 'Near normal'))

    def color_of(sn):
        r = rows.get(sn)
        v = metric(r) if r else None
        return None if v is None else round(to_t(v) * 20) / 20     # 21 color steps

    # ---- legend: what is measured, over what window, and what each state means
    if mode == 'Change':
        what = (f'<b>Change in daily mean flow</b> over the <b>{window} day{"s" if window > 1 else ""}</b> '
                f'ending <b>{end_label}</b>.')
        ticks = ['-50%', '-25%', '0', '+25%', '+50%']
        keys = [('▼', '#a51d2d', 'Dropping 5% or more'), ('●', '#8a857a', 'Within 5%'),
                ('▲', '#1c5aa6', 'Rising 5% or more'), ('○', T.STONE, 'No reading near this date')]
    else:
        what = (f'<b>Flow vs normal</b> on <b>{end_label}</b>: daily mean as a percent of the median '
                f'for that date in other years.')
        ticks = ['50%', '71%', '100%', '141%', '200%']
        keys = [('▼', '#a51d2d', 'Below 90% of normal'), ('●', '#8a857a', '90 to 110%'),
                ('▲', '#1c5aa6', 'Above 110% of normal'), ('○', T.STONE, 'No reading or no normal yet')]
    hist_note = ' <span class="rr-pill warn">Past date</span>' if historical else ''
    st.markdown(
        f'<div class="rr-legend" role="note" aria-label="Map legend">'
        f'<div class="what">{what}{hist_note} Each river takes the color of the gauge just below it.</div>'
        f'<div class="ramp" aria-hidden="true"><div class="bar" style="background:{T.ramp_css()}"></div>'
        f'<div class="ticks">' + ''.join(f'<span>{t}</span>' for t in ticks) + '</div></div>'
        '<div class="keys">' + ''.join(
            f'<span class="key"><span class="rr-sym" style="color:{c}" aria-hidden="true">{sym}</span>{T.esc(lab)}</span>'
            for sym, c, lab in keys) + '</div></div>', unsafe_allow_html=True)

    # ---- find a gauge (keyboard-friendly way in, and a summary card)
    in_view = set(order)
    keep_valid('map_find', [None] + order)
    find = st.selectbox('Find a gauge', [None] + order, key='map_find', placeholder='Type a river or town',
                        format_func=lambda s: 'All gauges' if s is None else f'{labels[s]}',
                        help='Centers the map on one gauge and shows its numbers.')

    mean_flow = {k: (float(m) if pd.notna(m := g['flow_cfs'].mean()) else 0.0) for k, g in A._groups(df).items()}
    feats = [f for f in reaches()['features'] if f['properties']['site_no'] in labels]
    # Draw "below the gauge" stretches first (small rivers first so a big river's color wins
    # below a confluence), then each gauge's own reach with big rivers first and small on top.
    # Lines that share a color and width go in one trace so the map stays quick with 200 gauges.
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
        w = round(0.9 + 0.75 * math.log10(max(mean_flow.get(sn, 10), 10)), 1)
        k = (color_of(sn), w)
        if k != batch_key:
            flush()
            batch_key, lon, lat = k, [], []
        for line in f['geometry']['coordinates']:
            lon += [p[0] for p in line] + [None]
            lat += [p[1] for p in line] + [None]
    flush()

    site_xy = sites.set_index('site_no')
    site_xy = site_xy[pd.to_numeric(site_xy['lon'], errors='coerce').notna()]
    mk = [s for s in order_all if s in site_xy.index]
    vals = [metric(rows[s]) if s in rows else None for s in mk]

    def tip(s, v):
        r = rows.get(s)
        sym, word = state(v)
        head = f"<b>{T.esc(labels[s])}</b><br>"
        if r is None:
            return head + 'No reading near this date (seasonal gauge or off)'
        if mode == 'Change':
            ch = 'under 1 cfs, no %' if r['change_pct'] is None else f"{r['change_pct']:+.0f}%"
            return (head + f"{sym} {word} {ch}<br>{r['start_cfs']:,.0f} → {r['end_cfs']:,.0f} cfs"
                    f"<br>{T.date(r['start_date'], False)} to {T.date(r['end_date'])}")
        pm = 'no normal yet' if r['pct_of_median'] is None else f"{r['pct_of_median']:.0f}% of normal"
        return head + f"{sym} {word}: {pm}<br>{r['end_cfs']:,.0f} cfs on {T.date(r['end_date'])}"

    lons, lats = pd.to_numeric(site_xy.loc[mk, 'lon']), pd.to_numeric(site_xy.loc[mk, 'lat'])
    fig.add_trace(go.Scattermap(lon=lons, lat=lats, mode='markers', marker=dict(size=12, color='white'),
                                hoverinfo='skip', showlegend=False))
    fig.add_trace(go.Scattermap(
        lon=lons, lat=lats, mode='markers',
        marker=dict(size=8.5, color=[T.OFF_SEASON if v is None else T.diverging_color(to_t(v)) for v in vals]),
        text=[tip(s, v) for s, v in zip(mk, vals)], hoverinfo='text', showlegend=False))

    # Label only the biggest movers in view, with the sign spelled out, so labels don't pile up
    live = [r for r in fc.value if r['site_no'] in in_view and metric(r) is not None]
    if mode == 'Change':
        movers = sorted([r for r in live if r['change_pct'] <= -5], key=metric)[:4] + \
                 sorted([r for r in live if r['change_pct'] >= 5], key=metric, reverse=True)[:4]
        lab = lambda r: f"{r['change_pct']:+.0f}%"
    else:
        movers = sorted([r for r in live if r['pct_of_median'] <= 90], key=metric)[:4] + \
                 sorted([r for r in live if r['pct_of_median'] >= 110], key=metric, reverse=True)[:4]
        lab = lambda r: f"{r['pct_of_median']:.0f}%"
    movers = [r for r in movers if r['site_no'] in site_xy.index]
    if movers:
        fig.add_trace(go.Scattermap(
            lon=[float(site_xy.loc[r['site_no'], 'lon']) for r in movers],
            lat=[float(site_xy.loc[r['site_no'], 'lat']) for r in movers],
            mode='text', text=[lab(r) for r in movers], textposition='top right',
            textfont=dict(size=12, color=T.INK), hoverinfo='skip', showlegend=False))

    clat, clon, zoom = config.REGION_VIEW.get(region, config.REGION_VIEW['All Montana'])
    if find:
        flat, flon = float(site_xy.loc[find, 'lat']), float(site_xy.loc[find, 'lon'])
        fig.add_trace(go.Scattermap(lon=[flon], lat=[flat], mode='markers', hoverinfo='skip', showlegend=False,
                                    marker=dict(size=22, color=T.INK, opacity=.85)))
        fig.add_trace(go.Scattermap(lon=[flon], lat=[flat], mode='markers', hoverinfo='skip', showlegend=False,
                                    marker=dict(size=15, color='white')))
        v = metric(rows[find]) if find in rows else None
        fig.add_trace(go.Scattermap(lon=[flon], lat=[flat], mode='markers', hoverinfo='text', showlegend=False,
                                    text=[tip(find, v)],
                                    marker=dict(size=10, color=T.OFF_SEASON if v is None else T.diverging_color(to_t(v)))))
        clat, clon, zoom = flat, flon, 8.3
    fig.update_layout(map=dict(style='carto-positron', center=dict(lat=clat, lon=clon), zoom=zoom),
                      height=600, margin=dict(l=0, r=0, t=0, b=0), uirevision=f'{region}-{find}',
                      hoverlabel=dict(bgcolor=T.SURFACE, bordercolor=T.RULE, font=dict(color=T.INK, size=13)))

    if find:
        r = rows.get(find)
        sym, word = state(metric(r) if r else None)
        if r:
            body = (f'<span>{sym} <b>{word}</b></span>'
                    f'<span>Flow <b>{r["end_cfs"]:,.0f} cfs</b> on {T.date(r["end_date"])}</span>'
                    f'<span>{window}-day change <b>'
                    + ('n/a' if r['change_pct'] is None else f'{r["change_pct"]:+.0f}%') + '</b>'
                    f' ({r["start_cfs"]:,.0f} cfs on {T.date(r["start_date"], False)})</span>'
                    f'<span>Vs normal <b>' + ('n/a' if r['pct_of_median'] is None else f'{r["pct_of_median"]:.0f}%')
                    + '</b></span>' + ('<span class="rr-pill warn">Provisional</span>' if r['status'] == 'Provisional' else ''))
        else:
            body = '<span>No reading near this date. Seasonal gauges shut off in fall and winter.</span>'
        st.markdown(f'<div class="rr-card" role="region" aria-label="Selected gauge">'
                    f'<div class="name">{T.esc(labels[find])}</div>'
                    f'<div class="meta">USGS {find} · {T.esc(reg_of.get(find, ""))}</div>'
                    f'<div class="row">{body}</div></div>', unsafe_allow_html=True)

        def open_history(sn=find):
            ss['page'] = '3  History'
            ss['hist_gauge'] = sn
        st.button('Open this gauge in History', on_click=open_history, key='map_to_hist')

    if not feats:
        T.note('River lines did not load, so the map shows gauge dots only. The numbers below are unaffected.',
               error=True)
    st.plotly_chart(fig, width='stretch', config={'displayModeBar': False, 'scrollZoom': True,
                                                   'displaylogo': False})
    st.caption('Drag to pan, scroll or pinch to zoom. Hover or tap a gauge dot for its numbers. Labeled dots '
               'are the biggest movers in view. If the background map does not load, rivers and gauges '
               'still draw, and the table below lists every reading.')

    if live:
        lo = min(live, key=metric)
        hi = max(live, key=metric)
        fmt = (lambda v: f'{v:+.0f}%') if mode == 'Change' else (lambda v: f'{v:.0f}%')
        if mode == 'Change':
            k1 = ('▲ Rising 5%+', sum(1 for r in live if r['change_pct'] >= 5))
            k2 = ('▼ Dropping 5%+', sum(1 for r in live if r['change_pct'] <= -5))
        else:
            k1 = ('▲ Above normal', sum(1 for r in live if r['pct_of_median'] >= 110))
            k2 = ('▼ Below normal', sum(1 for r in live if r['pct_of_median'] <= 90))
        T.stats([(k1[0], str(k1[1]), f'of {len(live)} gauges'), (k2[0], str(k2[1]), f'of {len(live)} gauges'),
                 ('Biggest drop' if mode == 'Change' else 'Lowest', fmt(metric(lo)), lo['gauge']),
                 ('Biggest rise' if mode == 'Change' else 'Highest', fmt(metric(hi)), hi['gauge'])])
    else:
        T.note('No gauges in this region had a reading near this date. Try a date in spring or summer, or '
               'pick another region.')

    T.figure(1, 'Every gauge, ranked',
             f"{'Change over ' + str(window) + ' days' if mode == 'Change' else 'Percent of normal'} "
             f'ending {end_label}, {WHERE}.')
    ranked = sorted((r for r in fc.value if r['site_no'] in in_view),
                    key=lambda r: (metric(r) is None, metric(r) or 0))
    default('map_all', False)
    show_all = st.toggle('Show every gauge', key='map_all') or len(ranked) <= 30
    shown = ranked if show_all else ranked[:10] + ranked[-10:]
    trows = []
    for r in shown:
        v = metric(r)
        sym, word = state(v)
        sw = T.OFF_SEASON if v is None else T.diverging_color(to_t(v))
        trows.append({'dir_html': f'<span style="color:{sw};font-weight:700" aria-hidden="true">{sym}</span> {word}',
                      'gauge': r['gauge'], 'river': r['river'],
                      'start': f"{r['start_cfs']:,.0f}", 'end': f"{r['end_cfs']:,.0f}",
                      'chg': '–' if r['change_pct'] is None else f"{r['change_pct']:+.0f}%",
                      'norm': '–' if r['pct_of_median'] is None else f"{r['pct_of_median']:.0f}%"})
    if not show_all and len(ranked) > 20:
        st.caption(f'Showing the 10 lowest and 10 highest of {len(ranked)} gauges with a reading.')
    if trows:
        T.table(trows, [('dir_html', 'State'), ('gauge', 'Gauge'), ('river', 'River'), ('start', 'Start cfs'),
                        ('end', 'End cfs'), ('chg', 'Change'), ('norm', 'Vs normal')],
                num=('start', 'end', 'chg', 'norm'))
    off = [labels[s] for s in order if s not in rows]
    if off:
        st.caption(f'{len(off)} gauge{"s" if len(off) > 1 else ""} had no reading near {end_label} '
                   '(seasonal gauges shut off in fall and winter): ' + ', '.join(off[:15])
                   + (f', and {len(off) - 15} more' if len(off) > 15 else '') + '.')
    for c in fc.caveats:
        if not c.startswith('No flow near'):
            st.caption(c)

# ---------------- 2 Today ----------------

elif page.endswith('Today'):
    cc = conditions_cached(DATA_KEY, tuple(order))
    rows = cc.value
    T.masthead(WHERE, f'Rivers on {LAST:%A}, {T.date(LAST)}',
               'The newest daily mean flow at each gauge, next to what is normal for that date. '
               '"Normal" is the median for the same calendar day across the gauge\'s other years.')
    status_line()
    if not rows:
        T.note('No gauges in this region have a recent reading. Seasonal gauges shut off in fall and winter.')
        st.stop()
    near = [r for r in rows if r['pct_of_median'] is not None] or rows
    hi = max(near, key=lambda r: r['pct_of_median'] or 0)
    lo = min(near, key=lambda r: r['pct_of_median'] or 0)
    temps = [r for r in rows if r['water_temp_max_f'] is not None and r['site_no'] not in config.THERMAL]
    warm = max(temps, key=lambda r: r['water_temp_max_f']) if temps else None
    gg = next((r for r in rows if r['site_no'] == '06043500'), max(rows, key=lambda r: r['flow_cfs']))
    pm = lambda r: '–' if r['pct_of_median'] is None else f"{r['pct_of_median']:.0f}%"
    T.stats([
        (gg['gauge'], f"{gg['flow_cfs']:,.0f} cfs",
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
                      'date': T.date(r['date'], False), 'flags': flags})
    T.table(trows, [('gauge', 'Gauge'), ('flow', 'Flow cfs'), ('median', 'Normal cfs'), ('pct_html', 'Vs normal'),
                    ('chg', '7-day'), ('temp', 'Water max'), ('date', 'Reading'), ('flags', 'Notes')],
            num=('flow', 'median', 'chg', 'temp'))
    stale_c = [c for c in cc.caveats if 'Not current' in c]
    shaky = [c for c in cc.caveats if 'shaky' in c]
    if stale_c:
        st.caption(stale_c[0])
    if shaky:
        st.caption(f'{len(shaky)} gauge(s) have fewer than {A.MIN_NORMAL_YEARS} other years on record, so their '
                   '"normal" is rough.')
    st.caption('Provisional means USGS has not reviewed the value yet. It can change. Percent of normal is '
               f'left blank where normal flow is under {A.MIN_CHANGE_CFS:g} cfs. Warmest water leaves out '
               + ' and '.join(config.THERMAL.values()) + '.')

    T.figure(3, 'This water year against the record')
    keep_valid('today_gauge', order)
    default('today_gauge', order[pick_default(order)])
    pick = st.selectbox('Gauge', order, format_func=labels.get, key='today_gauge')
    wy = int(A._gauge(df, pick)['water_year'].max())
    if LAST.month == 10 or (LAST.month == 11 and LAST.day < 20):
        # Early in a water year there's only a few weeks of the new one, so open on the year just finished
        keep_valid('today_wy', [wy - 1, wy])
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
               'When each river peaks, what a normal month looks like, and how any stretch of days ranks '
               'against every earlier year at that gauge.')
    status_line()
    if not order:
        T.note('No gauges in this region.')
        st.stop()
    keep_valid('hist_gauge', order)
    default('hist_gauge', order[pick_default(order)])
    pick = st.selectbox('Gauge', order, format_func=labels.get, key='hist_gauge')
    pk = A.annual_peaks(df, pick)
    if pk.error or not pk.value:
        T.note(pk.error or f'{labels[pick]} has no flow readings to summarize.', error=True)
        st.stop()
    tr = A.runoff_timing_trend(df, pick)
    p = pd.DataFrame(pk.value)
    full = p[p['days_with_data'] >= A.FULL_YEAR_DAYS]
    big = full.loc[full['peak_cfs'].idxmax()] if len(full) else None
    T.stats([
        ('Years of record', f'{len(full)}', f"full water years since {int(p['water_year'].min())}"),
        ('Median peak date', tr.value['median_peak_date'] if not tr.error else '–', 'daily mean peak'),
        ('Biggest peak', T.cfs(big['peak_cfs']) + ' cfs' if big is not None else '–',
         T.date(big['peak_date']) if big is not None else 'no full years yet'),
        ('Timing trend', f"{tr.value['days_per_decade']:+.1f} d/decade" if not tr.error else '–',
         f"R² {tr.value['r_squared']:.2f}, mostly noise" if not tr.error and tr.value['r_squared'] < .2 else
         (f"R² {tr.value['r_squared']:.2f}" if not tr.error else 'needs 8 full years')),
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
    fig.update_layout(height=320, yaxis=dict(tickformat='%b %d', title='Peak date'),
                      xaxis=dict(title='Water year', tickformat='d'))
    if pf.empty:
        T.note('No full water years at this gauge yet, so there are no peaks to plot.')
    else:
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
        fig.update_layout(height=300, yaxis_title='Median flow (cfs)', margin=dict(t=24))
        st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
    with c2:
        T.figure(6, 'Any window vs every earlier year')
        g = A._gauge(df, pick)
        default('hist_win', ((LAST - pd.Timedelta(days=29)).date(), LAST.date()))
        if isinstance(ss['hist_win'], tuple) and ss['hist_win'] and ss['hist_win'][0] < g['date'].min().date():
            ss['hist_win'] = ((LAST - pd.Timedelta(days=29)).date(), LAST.date())
        d0 = st.date_input('Window (pick a start and an end)', min_value=g['date'].min(), max_value=LAST,
                           key='hist_win', format='MM/DD/YYYY')
        if not (isinstance(d0, tuple) and len(d0) == 2):
            st.caption('Pick an end date to finish the window.')
        else:
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
    status_line()
    if not with_temp:
        T.note('No gauges in this region have a water temperature sensor with recent readings. '
               'Try Southwest or Western.')
        st.stop()
    keep_valid('temp_gauge', with_temp)
    default('temp_gauge', with_temp[pick_default(with_temp, '06052500')])
    pick = st.selectbox('Gauge (only gauges with a recent temperature sensor)', with_temp,
                        format_func=labels.get, key='temp_gauge')
    by = A.hot_water_by_year(df, pick)
    yrs = pd.DataFrame(by.value)
    yrs = yrs[yrs['summer_days_with_temp'] >= 60]
    if yrs.empty:
        T.note(f'{labels[pick]} has no summer with 60 or more days of temperature readings yet.')
        st.stop()
    T.figure(7, 'Days at or above 73°F, by year', 'Years with fewer than 60 summer readings are left out.')
    fig = go.Figure(go.Bar(x=yrs['year'], y=yrs['days_at_or_above'],
                           marker_color=[T.HOT if d > 0 else T.RULE for d in yrs['days_at_or_above']],
                           text=yrs['days_at_or_above'], textposition='outside',
                           hovertemplate='%{x}: %{y} days, hottest %{customdata:.1f}°F<extra></extra>',
                           customdata=yrs['hottest_f']))
    fig.update_layout(height=280, yaxis_title='Days', xaxis=dict(dtick=1, tickangle=-45))
    st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})

    years = sorted(int(y) for y in yrs['year'])
    keep_valid('temp_year', years)
    default('temp_year', years[-1])
    year = st.select_slider('Year', options=years, key='temp_year') if len(years) > 1 else years[0]
    hw = A.hot_water_days(df, pick, year)
    if hw.error:
        T.note(hw.error)
    else:
        v = hw.value
        T.stats([('Days ≥ 73°F', str(v['days_at_or_above']), f'{year}'),
                 ('Hottest', f"{v['hottest_f']:.1f}°F", T.date(v['hottest_date'], False)),
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
        fig.update_layout(height=320, yaxis_title='Water temperature (°F)', hovermode='x unified')
        st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
        st.caption('Shaded spans are runs of 3+ days at or above 73°F. ' + ' '.join(hw.caveats[1:]))

# ---------------- 4 Ask ----------------

elif page.endswith('Ask'):
    T.masthead('Ask', 'Questions about the rivers',
               'Every number comes from a calculation on the loaded data. The method under each answer '
               'shows exactly which tool ran.')
    key = secret('GEMINI_API_KEY')
    models = tuple(m for m in [secret('GEMINI_MODEL'), 'gemini-3-flash-preview', 'gemini-2.5-flash'] if m)
    status_line()
    st.caption(('Gemini is on.' if key else 'No Gemini key is set, so a keyword router answers.')
               + f' Ask looks at all {len(order_all)} gauges, whatever region is picked. '
               + f'{config.QUESTION_LIMIT - ss.asked} questions left this session.')
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
            T.note('That is the question limit for this session. Reload the page to start over.')
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
               f'USGS daily values, provisional and approved, for {df["site_no"].nunique()} gauges from water '
               'year 2001 on. A reading is the mean flow for one whole day, so the newest one is usually yesterday.')
    status_line()
    T.stats([('Daily rows', f'{len(df):,}', 'one per gauge per day'),
             ('Gauges', str(df['site_no'].nunique()), f"{len(recent_temp)} with recent water temp"),
             ('First reading', T.date(df['date'].min()), ''),
             ('Newest reading', T.date(LAST), ss.data_origin)])

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
            now = pd.Timestamp.now(tz='America/Denver')
            ss.daily_src = 'Snapshot + USGS refresh'
            ss.data_origin = f'refreshed from USGS {T.date(now)} at {now:%-I:%M %p} MT'
            st.toast(f'Got {len(fresh):,} recent rows from USGS.')
            st.rerun()
        except Exception as e:
            T.note(f'The USGS refresh did not work ({e}). Nothing changed: the app is still using '
                   f'{ss.data_origin}.', error=True)
    c2.caption('Without a USGS API key, USGS allows only a few requests per hour. A free key goes in '
               'the app secrets as USGS_API_KEY.')

    T.figure(10, 'Upload changed data', 'Replaces just that table. Use this for the validation tests.')
    up = st.file_uploader('Daily values or sites file (CSV, or CSV.GZ)', type=['csv', 'gz'], key='upload')
    if up is not None:
        h = hashlib.md5(up.getvalue()).hexdigest()
        if ss.get('last_upload') != h:
            name = up.name.lower()
            if any(k in name for k in config.FILES['sites']):
                ss.sites_bytes, ss.sites_src = up.getvalue(), f'Uploaded {up.name}'
            elif any(k in name for k in config.FILES['daily']):
                ss.daily_bytes, ss.daily_src = up.getvalue(), f'Uploaded {up.name}'
                ss.data_origin = f'uploaded file {up.name}'
            else:
                T.note('File name must contain "daily" or "sites" so the app knows which table it replaces.')
                st.stop()
            ss.last_upload = h
            st.rerun()
    if st.button('Restore original data'):
        ss.daily_bytes = (ROOT / 'data' / 'daily_values.csv.gz').read_bytes()
        ss.sites_bytes = (ROOT / 'data' / 'sites.csv').read_bytes()
        ss.daily_src, ss.sites_src, ss.last_upload = 'Snapshot in data/daily_values.csv.gz', 'data/sites.csv', None
        ss.data_origin = snapshot_origin()
        st.rerun()
    tot = df['flow_cfs'].sum()
    st.caption(f'Check sum: total of all daily flows = {tot:,.0f} cfs-days. Sites from {ss.sites_src}.')

    T.figure(11, 'Load notes', 'Anything odd the app found while loading. Nothing is dropped without a note here.')
    for n in notes:
        T.note(n['message'], ok=n['level'] == 'ok')
    if SNAP:
        st.caption(f"Snapshot: {SNAP.get('source', '')}. Downloaded {T.date(SNAP['downloaded'])}. "
                   f"{SNAP.get('note', '')}")

    T.figure(12, 'Data quality by gauge',
             'Provisional = not yet reviewed by USGS. Estimated days are mostly winter ice.')
    q = A.data_quality_report(df, notes).value['gauges']
    for row in q:
        row['first'], row['last'] = T.date(row['first']), T.date(row['last'])
    T.table(q, [('gauge', 'Gauge'), ('first', 'First'), ('last', 'Last'), ('missing_flow_days', 'Missing'),
                ('provisional_pct', 'Prov. %'), ('estimated_days', 'Estimated'), ('ice_days', 'Ice'),
                ('temp_days', 'Temp days')],
            num=('missing_flow_days', 'provisional_pct', 'estimated_days', 'ice_days', 'temp_days'))
    st.download_button(f'Download daily data for {region} (CSV)', region_csv(DATA_KEY, region),
                       f"daily_values_{region.lower().replace(' ', '_')}.csv", 'text/csv')

T.colophon('Data: U.S. Geological Survey daily values (NWIS), refreshed through the USGS Water Data API. '
           'River lines: USGS NHDPlus via NLDI. Basemap: © OpenStreetMap contributors, © CARTO. '
           'Recent values are provisional. Not a safety tool; check conditions and FWP rules before you go.')
