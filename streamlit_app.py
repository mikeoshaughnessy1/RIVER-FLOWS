"""Montana River Report: layout only. Data loading lives in data_prep, math in analytics,
the assistant in agent, looks in theme."""
from __future__ import annotations
import gzip
import hashlib
import io
import math
import pathlib
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

import agent
import analytics as A
import config
import data_prep as dp
import theme as T
import usgs

ROOT = pathlib.Path(__file__).parent
SNAPSHOT_SRC = 'Snapshot in data/daily_values.csv.gz'
st.set_page_config(page_title='Montana River Report', page_icon='🎣', layout='wide')
T.inject()


# ---------------- data ----------------

@st.cache_resource(show_spinner=False, max_entries=2)
def build_cached(daily_bytes: bytes, sites_bytes: bytes, recent_bytes: bytes):
    # Keyed on file CONTENTS, so changed data never shows old numbers. A shared resource, not
    # cache_data: that hands every rerun a new 100 MB copy, and analytics._groups kept a split
    # of each copy. Nothing may change this table in place.
    daily = dp.read_csv(daily_bytes)
    if recent_bytes:
        daily = dp.overlay(daily, dp.read_csv(recent_bytes))
    return dp.build(daily, dp.read_csv(sites_bytes))


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_recent(start: str, api_key: str | None, _salt: str):
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


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_style():
    r = requests.get(T.STYLE_URL, timeout=4)
    r.raise_for_status()
    return r.json()


def basemap():
    try:
        # Styled outside the cache, so a theme change shows up without waiting a day.
        return {**T.with_imagery(fetch_style()), 'id': 'field'}     # without a stable id Plotly reloads the style and drops layers
    except (requests.RequestException, ValueError):      # raises, so a failure isn't cached for a day
        return T.BLANK_MAP


@st.cache_data(show_spinner=False)
def boat_ramps():
    p = ROOT / 'data' / 'boat_ramps.csv'
    return pd.read_csv(p) if p.exists() else pd.DataFrame(columns=['name', 'lat', 'lon', 'boat_fac'])


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


def recent_file():
    """(bytes, downloaded) of the daily job's file. Empty if it isn't there or can't be read."""
    import json
    try:
        return ((ROOT / 'data' / 'recent.csv.gz').read_bytes(),
                json.loads((ROOT / 'data' / 'recent.json').read_text())['downloaded'])
    except (OSError, ValueError, KeyError):
        return b'', None


def snapshot_origin():
    got = recent_file()[1]
    if got:
        t = pd.Timestamp(got)
        return f'updated from USGS {T.date(t)} at {t:%-I:%M %p} MT'
    d = SNAP.get('downloaded')
    return f'snapshot downloaded {T.date(d)}' if d else 'bundled snapshot'


PAGES = ['Map', 'Today', 'History', 'Water temp', 'Ask', 'Data']
# shortcut: Streamlit can't see the screen width, so this reads the browser name. Tablets get the
# desktop view. Upgrade if a width-aware map component ever comes in.
PHONE = 'Mobi' in st.context.headers.get('User-Agent', '')

ss = st.session_state
if 'daily_bytes' not in ss:
    ss.daily_bytes = (ROOT / 'data' / 'daily_values.csv.gz').read_bytes()
    ss.sites_bytes = (ROOT / 'data' / 'sites.csv').read_bytes()
    ss.daily_src = SNAPSHOT_SRC
    ss.sites_src = 'data/sites.csv'
    ss.answers, ss.asked = [], 0
# Set apart from the block above: a tab left open across a deploy has daily_bytes but not this.
# Without an upload or refresh, always use today's file. A tab on an old one would rebuild a
# table the cache already dropped, and push out the table everyone else is using.
if ss.daily_src == SNAPSHOT_SRC:
    ss.recent_bytes = recent_file()[0]
    ss.data_origin = snapshot_origin()
elif 'recent_bytes' not in ss:
    ss.recent_bytes = b''

# Streamlit forgets a widget's value when its page isn't on screen. Re-assigning keeps the
# map date, window, region and gauge picks when you move between sections and come back.
PERSIST = ('region', 'map_land', 'map_ramps', 'map_mode', 'map_window', 'map_date', 'map_all', 'map_find', 'today_gauge', 'today_wy',
           'hist_gauge', 'hist_win', 'temp_gauge', 'temp_year')
for _k in PERSIST:
    if _k in ss:
        ss[_k] = ss[_k]

# ---------------- top bar ----------------

with st.container(key='topbar', horizontal=True, horizontal_alignment='distribute', vertical_alignment='bottom'):
    T.brand('River Report', 'Montana & Yellowstone field report from USGS gauges')
    region = st.selectbox('Region', ['All Montana'] + config.REGIONS, key='region', width=210,
                          help='Filters the map, gauge lists and download. Ask always sees every gauge.')
with st.container(key='nav'):
    page = st.radio('Section', PAGES, key='page', horizontal=True, label_visibility='collapsed')

try:
    df, sites, notes = build_cached(ss.daily_bytes, ss.sites_bytes, ss.recent_bytes)
except ValueError as e:
    T.masthead('Montana River Report', 'The data could not be loaded',
               'The file that was loaded is missing something the app needs. Nothing below is shown '
               'until the data is fixed, so no numbers are guessed.')
    T.note(str(e), error=True)
    if st.button('Restore the original data', type='primary'):
        for k in ('daily_bytes', 'sites_bytes', 'recent_bytes', 'last_upload'):
            ss.pop(k, None)
        ss.upload_n = ss.get('upload_n', 0) + 1      # new key empties the uploader, or it re-applies the bad file
        st.rerun()
    st.stop()

LAST = df['date'].max()
DATA_KEY = dp.data_key(ss.daily_bytes, ss.sites_bytes, ss.recent_bytes)
labels = sites.set_index('site_no')['label'].to_dict()
present = set(df['site_no'].unique())
labels = {s: labels.get(s, s) for s in df['site_no'].cat.categories if s in present}
reg_of = sites.set_index('site_no')['region'].to_dict()
listed = set(sites['site_no'])
order_all = [s for s in sites['site_no'] if s in labels] + sorted(s for s in labels if s not in listed)
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


@st.cache_data(show_spinner=False, max_entries=4)
def mean_flows(key):
    return {k: (float(m) if pd.notna(m := g['flow_cfs'].mean()) else 0.0) for k, g in A._groups(df).items()}


@st.cache_data(show_spinner='Checking the data', max_entries=4)
def quality_cached(key):
    return A.data_quality_report(df, notes).value['gauges']


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


def clamp(d, lo, hi):
    return min(max(d, lo), hi)


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
    if STALE:
        parts.append(f'The newest reading is {AGE_DAYS} days old. Refresh it on the Data page.')
    T.status(parts, stale=STALE)
    if warns and page != 'Data':
        def see_notes():
            ss['page'] = 'Data'
        st.button(f'⚠️ {len(warns)} data note{"s" if len(warns) > 1 else ""}: see Data', key='to_data',
                  type='tertiary', on_click=see_notes)


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
    if p < 75:
        return f'<span class="rr-pill low">▼ {p:,.0f}%</span>'
    return f'<span class="rr-pill high">▲ {p:,.0f}%</span>' if p > 130 else f'<span class="rr-pill">{p:,.0f}%</span>'


# ---------------- 1 Map ----------------

if page.endswith('Map'):
    head = st.container()      # filled below: the headline needs the numbers the controls pick
    # A click on a gauge lands here before the widgets draw. Handle each new click once, because
    # the chart keeps reporting its last selection on every rerun.
    pts = ((ss.get('map_chart') or {}).get('selection') or {}).get('points') or []
    clicked = None
    if pts != ss.get('map_seen', []):
        ss['map_seen'] = pts
        clicked = next((p['customdata'] for p in pts if p.get('customdata') in labels), None)
        if clicked:
            ss['map_find'], ss['map_clicked'] = clicked, clicked

    with st.container(key='controls'):
        box = st.expander('Map options') if PHONE else st.container()    # keeps the map on a phone's first screen
    with box:
        c1, c2, c3, c4 = st.columns([1.05, 1.2, 1, 1.5], gap='medium')
        with st.container(horizontal=True, gap='medium'):
            land = st.toggle('Public land', key='map_land',
                             help='BLM map of who manages the land. Check boundaries before you rely on them for access.')
            ramps = st.toggle('Boat ramps', key='map_ramps', help='Montana FWP ramps for trailered boats. Check the site before you tow.')
    mode = c1.radio('Color rivers by', ['Change', 'Vs normal'], horizontal=True, key='map_mode',
                    help='Change: percent change in daily flow over the window. Vs normal: flow on the '
                         'end date as a percent of the median for that calendar day in other years.')
    default('map_window', 7)
    window = c2.select_slider('Change window', [1, 3, 7, 14, 30], key='map_window',
                              format_func=lambda d: f'{d} day' + ('s' if d > 1 else ''),
                              disabled=mode != 'Change',
                              help='Only used when coloring by change.')
    hi_d = LAST.date()
    lo_d = min((df['date'].min() + pd.Timedelta(days=31)).date(), hi_d)
    if ss.get('map_newest') != hi_d:          # new data: a date left on the newest reading moves with it
        if ss.get('map_date') == ss.get('map_newest'):
            ss.pop('map_date', None)
        ss['map_newest'] = hi_d
    default('map_date', hi_d)
    ss['map_date'] = clamp(ss['map_date'] or hi_d, lo_d, hi_d)      # blank box, or data swapped for another file
    as_of = c3.date_input('As of', min_value=lo_d, max_value=hi_d, key='map_date', format='MM/DD/YYYY',
                          help=f'Any day from {T.date(lo_d)} to the newest reading, {T.date(hi_d)}.')
    keep_valid('map_find', [None] + order)
    find = c4.selectbox('Find a gauge', [None] + order, key='map_find', placeholder='Type a river or town',
                        format_func=lambda s: 'All gauges' if s is None else f'{labels[s]}',
                        help='Centers the map on one gauge and shows its numbers. Clicking a dot does too.')

    fc = change_cached(DATA_KEY, str(as_of), window)
    if fc.error:
        with head:
            T.masthead(WHERE, 'Rivers rising and dropping', 'This date could not be shown.')
            status_line()
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
        return None if v is None else round(to_t(v) * 40) / 40     # 41 color steps, so the 5% band lands on a step

    def shade(v):
        return T.OFF_SEASON if v is None else T.diverging_color(to_t(v))

    # ---- headline: what changed, where
    in_view = set(order)
    live = [r for r in fc.value if r['site_no'] in in_view and metric(r) is not None]
    fmt = (lambda v: f'{v:+.0f}%') if mode == 'Change' else (lambda v: f'{v:.0f}%')
    ups = sum(1 for r in live if state(metric(r))[0] == '▲')
    downs = sum(1 for r in live if state(metric(r))[0] == '▼')
    gauges = lambda n: f'{n} gauge' + ('' if n == 1 else 's')
    if live:
        lo, hi = min(live, key=metric), max(live, key=metric)
        if mode == 'Change':
            title = f'{gauges(downs)} dropping, {ups} rising'
            span = f'Over the {window} day{"s" if window > 1 else ""} ending {end_label}.'
            ends = f'Biggest drop: {lo["gauge"]}, {fmt(metric(lo))}. Biggest rise: {hi["gauge"]}, {fmt(metric(hi))}.'
        else:
            title = f'{gauges(downs)} below normal, {ups} above'
            span = f'On {end_label}.'
            ends = f'Lowest: {lo["gauge"]}, {fmt(metric(lo))}. Highest: {hi["gauge"]}, {fmt(metric(hi))}.'
        sub = f'{span} {ends} {len(live)} of {len(order)} gauges have a usable reading.'
    else:
        title = 'No readings near this date'
        sub = 'Seasonal gauges shut off in fall and winter. Try a date in spring or summer, or another region.'
    with head:
        T.masthead(WHERE + (' · past date' if historical else ''), title, sub)
        status_line()

    # ---- legend: what is measured, over what window, and what each state means
    if mode == 'Change':
        what = (f'<b>Change in daily mean flow</b> over the <b>{window} day{"s" if window > 1 else ""}</b> '
                f'ending <b>{end_label}</b>.')
        ticks = ['-50%', '-25%', '0', '+25%', '+50%']
        keys = [('▼', T.diverging_color(0), 'Dropping 5% or more'), ('●', T.diverging_color(.5), 'Within 5%'),
                ('▲', T.diverging_color(1), 'Rising 5% or more'), ('○', T.STONE, 'No reading near this date')]
    else:
        what = (f'<b>Flow vs normal</b> on <b>{end_label}</b>: daily mean as a percent of the median '
                f'for that date in other years.')
        ticks = ['50%', '71%', '100%', '141%', '200%']
        keys = [('▼', T.diverging_color(0), 'Below 90% of normal'), ('●', T.diverging_color(.5), '90 to 110%'),
                ('▲', T.diverging_color(1), 'Above 110% of normal'), ('○', T.STONE, 'No reading or no normal yet')]
    if ramps:
        keys.append(('●', T.PINE, 'Boat ramp'))
    hist_note = ' <span class="rr-pill warn">Past date</span>' if historical else ''

    # Each stretch of river now has one owner, so draw order doesn't matter and lines can be
    # batched by color and width. That keeps the map to a few dozen traces.
    mean_flow = mean_flows(DATA_KEY)
    style = basemap()
    names_layer = next((x['id'] for x in style['layers'] if x['type'] == 'symbol'), '')   # rivers go under town names
    feats = [f for f in reaches()['features'] if f['properties']['site_no'] in in_view]
    fig = go.Figure()
    batches: dict = {}
    for f in feats:
        sn = f['properties']['site_no']
        flow = mean_flow.get(sn, 0)
        line = batches.setdefault((color_of(sn), 3.8 if flow >= 1000 else (2.8 if flow >= 100 else 2)), ([], []))
        for part in f['geometry']['coordinates']:
            line[0].extend([p[0] for p in part] + [None])
            line[1].extend([p[1] for p in part] + [None])
    # A dark edge under every river makes the colors stand out from the imagery
    edges = {}
    for (_, w), (lon, lat) in batches.items():
        edge = edges.setdefault(w, ([], []))
        edge[0].extend(lon)
        edge[1].extend(lat)
    for w, (lon, lat) in sorted(edges.items()):
        fig.add_trace(go.Scattermap(lon=lon, lat=lat, mode='lines', hoverinfo='skip', showlegend=False, below=names_layer,
                                    line=dict(color='rgba(0,0,0,.5)', width=w + 1.4)))
    # Pale "no reading" lines first, then thin to thick, so the big rivers read on top
    for (t, w), (lon, lat) in sorted(batches.items(), key=lambda kv: (kv[0][0] is not None, kv[0][1])):
        fig.add_trace(go.Scattermap(lon=lon, lat=lat, mode='lines', hoverinfo='skip', showlegend=False, below=names_layer,
                                    line=dict(color=T.OFF_SEASON if t is None else T.diverging_color(t), width=w)))

    site_xy = sites.set_index('site_no')
    site_xy = site_xy[pd.to_numeric(site_xy['lon'], errors='coerce').notna()]
    mk = [s for s in order if s in site_xy.index]
    vals = [metric(rows[s]) if s in rows else None for s in mk]

    def tip(s, v):
        r = rows.get(s)
        sym, word = state(v)
        head_ = f"<b>{T.esc(labels[s])}</b><br>"
        if r is None:
            return head_ + 'No reading near this date (seasonal gauge or off)'
        if mode == 'Change':
            ch = 'under 1 cfs, no %' if r['change_pct'] is None else f"{r['change_pct']:+.0f}%"
            return (head_ + f"{sym} {word} {ch}<br>{r['start_cfs']:,.0f} → {r['end_cfs']:,.0f} cfs"
                    f"<br>{T.date(r['start_date'], False)} to {T.date(r['end_date'])}")
        pm = 'no normal yet' if r['pct_of_median'] is None else f"{r['pct_of_median']:.0f}% of normal"
        return head_ + f"{sym} {word}: {pm}<br>{r['end_cfs']:,.0f} cfs on {T.date(r['end_date'])}"

    lons, lats = pd.to_numeric(site_xy.loc[mk, 'lon']), pd.to_numeric(site_xy.loc[mk, 'lat'])
    crowded = PHONE and region == 'All Montana'      # 199 dots on a phone: smaller, and too small for a mark
    fig.add_trace(go.Scattermap(lon=lons, lat=lats, mode='markers', marker=dict(size=8 if crowded else 13, color='white'),
                                hoverinfo='skip', showlegend=False))
    fig.add_trace(go.Scattermap(lon=lons, lat=lats, mode='markers', hoverinfo='skip', showlegend=False,
                                marker=dict(size=6 if crowded else 10, color=[shade(v) for v in vals])))
    # The dot's own direction mark, so a colorblind reader can see it without hovering
    marked = [(x, y, '+' if state(v)[0] == '▲' else '-') for x, y, v in zip(lons, lats, vals)
              if state(v)[0] in ('▲', '▼')]
    if marked and not crowded:
        fig.add_trace(go.Scattermap(lon=[m[0] for m in marked], lat=[m[1] for m in marked], mode='markers+text',
                                    text=[m[2] for m in marked], textposition='middle center', hoverinfo='skip',
                                    marker=dict(size=1, opacity=0),
                                    textfont=dict(size=11, color='white'), showlegend=False))

    clat, clon, zoom = config.REGION_VIEW.get(region, config.REGION_VIEW['All Montana'])
    zoom -= 1.55 if PHONE else 0

    # Label the biggest movers. Skip any that would land on a label already placed.
    live_mk = [r for r in live if r['site_no'] in site_xy.index]
    low_first = sorted((r for r in live_mk if state(metric(r))[0] == '▼'), key=metric)
    high_first = sorted((r for r in live_mk if state(metric(r))[0] == '▲'), key=metric, reverse=True)
    gap = 80 * 360 / (512 * 2 ** zoom)        # about 80 px, in degrees
    placed = []
    for r in [x for pair in zip(low_first, high_first) for x in pair] + low_first + high_first:
        x, y = float(site_xy.loc[r['site_no'], 'lon']), float(site_xy.loc[r['site_no'], 'lat'])
        if len(placed) < 8 and all(abs(x - p[0]) > gap or abs(y - p[1]) > gap / 2 for p in placed):
            placed.append((x, y, fmt(metric(r))))
    if placed:
        # mode 'text' alone has no marker size, so Plotly can't offset the text and the layer fails
        fig.add_trace(go.Scattermap(lon=[p[0] for p in placed], lat=[p[1] for p in placed], mode='markers+text',
                                    text=[p[2] for p in placed], textposition='top right', hoverinfo='skip',
                                    marker=dict(size=10, opacity=0),
                                    textfont=dict(size=12.5, color=T.INK if style is T.BLANK_MAP else 'white'), showlegend=False))

    has_xy = find in site_xy.index
    if find and has_xy:
        flat, flon = float(site_xy.loc[find, 'lat']), float(site_xy.loc[find, 'lon'])
        fig.add_trace(go.Scattermap(lon=[flon], lat=[flat], mode='markers', hoverinfo='skip', showlegend=False,
                                    marker=dict(size=24, color=T.INK, opacity=.85)))
        fig.add_trace(go.Scattermap(lon=[flon], lat=[flat], mode='markers', hoverinfo='skip', showlegend=False,
                                    marker=dict(size=17, color='white')))
        v = metric(rows[find]) if find in rows else None
        fig.add_trace(go.Scattermap(lon=[flon], lat=[flat], mode='markers', hoverinfo='skip', showlegend=False,
                                    marker=dict(size=11, color=shade(v))))
        if find != ss.get('map_clicked'):     # picked from the list: go there. Clicked: already looking at it.
            clat, clon, zoom = flat, flon, 8.3 - (.5 if PHONE else 0)
    # Invisible, wider than the dots, and last: an easy target for a finger or a mouse
    fig.add_trace(go.Scattermap(lon=lons, lat=lats, mode='markers', marker=dict(size=26, color=T.INK, opacity=.01),
                                text=[tip(s, v) for s, v in zip(mk, vals)], hoverinfo='text', customdata=mk,
                                unselected=dict(marker=dict(opacity=.01)), selected=dict(marker=dict(opacity=.01)),
                                showlegend=False))
    pts = boat_ramps() if ramps else None
    if ramps and len(pts):
        far = zoom < 6.5        # at state zoom full-size ramps bury the rivers and gauges
        fig.add_trace(go.Scattermap(lon=pts['lon'], lat=pts['lat'], mode='markers', showlegend=False, below=names_layer,
                                    marker=dict(size=6 if far else 11, color='white'), hoverinfo='skip'))
        fig.add_trace(go.Scattermap(lon=pts['lon'], lat=pts['lat'], mode='markers', showlegend=False, below=names_layer,
                                    marker=dict(size=3.5 if far else 7, color=T.PINE), hoverinfo='text',
                                    text='Boat ramp: ' + pts['name'].astype(str).map(T.esc)))
    fig.update_layout(map=dict(style=T.with_land(style, names_layer) if land else style,
                               center=dict(lat=clat, lon=clon), zoom=zoom),
                      height=440 if PHONE else 680, margin=dict(l=0, r=0, t=0, b=0),
                      uirevision=f'{region}-{find if find != ss.get("map_clicked") else "click"}',
                      hoverlabel=dict(bgcolor=T.SURFACE, bordercolor=T.RULE, font=dict(color=T.INK, size=13)))

    with st.container(key='mapbox', gap=None):
        st.markdown(
            f'<div class="rr-legend" role="note" aria-label="Map legend">'
            f'<div class="what">{what}{hist_note} Each river takes the color of the gauge just below it.</div>'
            f'<div class="ramp" aria-hidden="true"><div class="bar" style="background:{T.ramp_css()}"></div>'
            f'<div class="ticks">' + ''.join(f'<span>{t}</span>' for t in ticks) + '</div></div>'
            '<div class="keys">' + ''.join(
                f'<span class="key"><span class="rr-sym" style="color:{c}" aria-hidden="true">{sym}</span>{T.esc(lab)}</span>'
                for sym, c, lab in keys) + '</div></div>', unsafe_allow_html=True)
        st.plotly_chart(fig, width='stretch', key='map_chart', on_select='rerun', selection_mode='points',
                        config={'displaylogo': False, 'scrollZoom': not PHONE, 'displayModeBar': True,
                                'modeBarButtonsToRemove': ['toImage', 'pan2d', 'select2d', 'lasso2d']})
    if style is T.BLANK_MAP:
        T.note('The background map could not load, so towns and roads are missing. Rivers and gauges are unaffected.')
    if not feats:
        T.note('River lines did not load, so the map shows gauge dots only. The table below is unaffected.',
               error=True)
    st.caption(('Pinch to zoom, or use the + and - buttons. Tap a gauge for its numbers. ' if PHONE else
                'Drag to pan. Scroll or use the + and - buttons to zoom. Hover a gauge for its numbers, click to '
                'select it. ')
               + ('Pick a region to see + and - marks in the dots. ' if crowded else 'A + or - in a dot shows direction. ')
               + 'Labels mark the biggest movers. If the background map does '
                 'not load, rivers and gauges still draw, and the table below lists every reading.')

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
                    + '</b></span>')
        else:
            body = '<span>No reading near this date. Seasonal gauges shut off in fall and winter.</span>'
        now_row = next(iter(A.current_conditions(df, [find], str(as_of)).value), None)
        say = A.river_note(now_row).value if now_row and r else ''
        st.markdown(f'<div class="rr-card" role="region" aria-label="Selected gauge">'
                    f'<div class="name">{T.esc(labels[find])}</div>'
                    f'<div class="meta">USGS {find} · {T.esc(reg_of.get(find, ""))}</div>'
                    f'<div class="meta">{T.esc(say)}</div>'
                    f'<div class="row">{body}</div></div>', unsafe_allow_html=True)
        if not has_xy:
            st.caption('This gauge has no map location in the sites file, so it is not on the map.')

        def open_history(sn=find):
            ss['page'] = 'History'
            ss['hist_gauge'] = sn
        st.button('Open this gauge in History', on_click=open_history, key='map_to_hist')

    T.section('Every gauge, ranked',
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
        trows.append({'dir_html': f'<span style="color:{shade(v)};font-weight:700" aria-hidden="true">{sym}</span> {word}',
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
    rows = cc.value if order else []       # an empty list means "every gauge" to current_conditions
    T.masthead(WHERE, f'Rivers on {LAST:%A}, {T.date(LAST)}',
               'The newest daily mean flow at each gauge, next to what is normal for that date. '
               '"Normal" is the median for the same calendar day across the gauge\'s other years.')
    status_line()
    if not rows:
        T.note('No gauges in this region have a recent reading. Seasonal gauges shut off in fall and winter.')
        st.stop()
    # Seasonal gauges keep their last reading from weeks ago. It stays in the table, marked,
    # but it can't be today's highest, lowest or warmest.
    cutoff = LAST - pd.Timedelta(days=3)
    is_current = lambda r: pd.Timestamp(r['date']) >= cutoff
    fresh = [r for r in rows if is_current(r)]
    if fresh:
        near = [r for r in fresh if r['pct_of_median'] is not None]
        hi = max(near, key=lambda r: r['pct_of_median']) if near else None
        lo = min(near, key=lambda r: r['pct_of_median']) if near else None
        temps = [r for r in fresh if r['water_temp_max_f'] is not None and r['site_no'] not in config.THERMAL]
        warm = max(temps, key=lambda r: r['water_temp_max_f']) if temps else None
        gg = next((r for r in fresh if r['site_no'] == '06043500'), max(fresh, key=lambda r: r['flow_cfs']))
        pm = lambda r: '–' if r is None else f"{r['pct_of_median']:.0f}%"
        T.stats([
            (gg['gauge'], f"{gg['flow_cfs']:,.0f} cfs",
             '' if gg['pct_of_median'] is None else f"{gg['pct_of_median']:.0f}% of normal"),
            ('Highest vs normal', pm(hi), hi['gauge'] if hi else 'no normal yet'),
            ('Lowest vs normal', pm(lo), lo['gauge'] if lo else 'no normal yet'),
            ('Warmest water', f"{warm['water_temp_max_f']:.0f}°F" if warm else '–',
             warm['gauge'] if warm else 'no recent sensor reading'),
        ])
    else:
        T.note(f'No gauge here has a reading from the 3 days before {T.date(LAST)}. The table shows the last '
               'reading from each one.')

    T.section('River by river', 'Percent of median: under 75% is low for the date, over 130% is high.')
    pos = {s: i for i, s in enumerate(order)}
    by_area: dict = {}
    for r in sorted(rows, key=lambda r: pos.get(r['site_no'], 1e9)):
        area = by_area.setdefault(reg_of.get(r['site_no'], 'Other') if region == 'All Montana' else '', {})
        area.setdefault(r['river'], []).append(r)
    for area, rivers in by_area.items():
        if area:
            T.group(area)
        T.river_cards([{
            'name': river,
            'say': A.river_summary([g for g in gs if is_current(g)]).value,
            'lines': [(g['gauge'], T.cfs(g['flow_cfs']) + ' cfs',
                       pct_label(g['pct_of_median']) if is_current(g) else
                       f'<span class="rr-pill warn">{T.esc(T.date(g["date"], False))}</span>') for g in gs]}
            for river, gs in rivers.items()])

    trows, group = [], None
    group_by = 'river' if region != 'All Montana' else 'region'
    for r in sorted(rows, key=lambda r: pos.get(r['site_no'], 1e9)):
        g = r['river'] if group_by == 'river' else reg_of.get(r['site_no'], 'Other')
        if g != group:
            group = g
            trows.append({'_group': g})
        ch = r['change_7d_pct']
        flags = r['flags']
        trows.append({'gauge': r['gauge'], 'flow': T.cfs(r['flow_cfs']), 'median': T.cfs(r['median_cfs']),
                      'pct_html': pct_label(r['pct_of_median']),
                      'chg': '–' if ch is None else f'{ch:+.0f}%',
                      'temp': '–' if r['water_temp_max_f'] is None else f"{r['water_temp_max_f']:.0f}°F",
                      'date_html': T.esc(T.date(r['date'], False)) if is_current(r) else
                      f'<span class="rr-pill warn">{T.esc(T.date(r["date"]))}</span>', 'flags': flags})
    with st.expander('Every gauge as a table'):
        T.table(trows, [('gauge', 'Gauge'), ('flow', 'Flow cfs'), ('median', 'Normal cfs'), ('pct_html', 'Vs normal'),
                        ('chg', '7-day'), ('temp', 'Water max'), ('date_html', 'Reading'), ('flags', 'Notes')],
                num=('flow', 'median', 'chg', 'temp'))
    old = len(rows) - len(fresh)
    if old:
        st.caption(f'{old} of {len(rows)} gauges have no reading from the last 3 days. Their last reading is '
                   'marked in the Reading column and is left out of the numbers at the top.')
    shaky = [c for c in cc.caveats if 'shaky' in c]
    if shaky:
        st.caption(f'{len(shaky)} gauge(s) have fewer than {A.MIN_NORMAL_YEARS} other years on record, so their '
                   '"normal" is rough.')
    st.caption('Percent of normal is '
               f'left blank where normal flow is under {A.MIN_CHANGE_CFS:g} cfs. Warmest water leaves out '
               + ' and '.join(config.THERMAL.values()) + '.')

    T.section('This water year against the record')
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

    T.section('When the river peaked each year', 'Dot size is the peak flow. Earlier dots = earlier runoff.')
    pf = full.copy()
    pf['day'] = pd.to_datetime('2001-01-01') + pd.to_timedelta(pf['peak_day_of_year'] - 1, unit='D')
    fig = go.Figure(go.Scatter(
        x=pf['water_year'], y=pf['day'], mode='markers',
        marker=dict(size=(pf['peak_cfs'] / max(pf['peak_cfs'].max(), 1) * 26 + 6), color=T.RIVER, opacity=.75,
                    line=dict(color=T.PAPER, width=1)),
        customdata=list(zip(pf['peak_cfs'], pf['peak_date'].map(T.date))), hovertemplate='WY %{x}: %{customdata[0]:,.0f} cfs on %{customdata[1]}<extra></extra>'))
    fig.update_layout(height=320, yaxis=dict(tickformat='%b %d', title='Peak date'),
                      xaxis=dict(title='Water year', tickformat='d'))
    if pf.empty:
        T.note('No full water years at this gauge yet, so there are no peaks to plot.')
    else:
        st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})

    c1, c2 = st.columns([1, 1], gap='large')
    with c1:
        T.section('Typical flow by month')
        m = pd.DataFrame(A.monthly_flow(df, pick).value)
        mo = ['Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep']
        m = m.set_index('month').reindex(mo).reset_index()
        fig = go.Figure(go.Bar(x=m['month'], y=m['median_cfs'], marker_color=T.RIVER_LIGHT,
                               text=m['median_cfs'].map(lambda v: f'{v:,.0f}'), textposition='outside',
                               hovertemplate='%{x}: %{y:,.0f} cfs median<extra></extra>'))
        fig.update_layout(height=300, yaxis_title='Median flow (cfs)', margin=dict(t=24))
        st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
    with c2:
        T.section('Any window vs every earlier year')
        g = A._gauge(df, pick)
        lo_d, hi_d = g['date'].min().date(), LAST.date()
        last_30 = (clamp((LAST - pd.Timedelta(days=29)).date(), lo_d, hi_d), hi_d)
        default('hist_win', last_30)
        # A date outside this gauge's record, or past newer-than-loaded data, is an error in the widget
        if any(not lo_d <= d <= hi_d for d in ss['hist_win'] or ()):
            ss['hist_win'] = last_30
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
                         ('Percent', '–' if v['pct_of_median'] is None else f"{v['pct_of_median']:.0f}%", 'of normal'),
                         ('Rank', v['rank'].split(' (')[0], '1 = highest flow')])
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
    if by.error:
        T.note(by.error, error=True)
        st.stop()
    yrs = pd.DataFrame(by.value)
    yrs = yrs[yrs['summer_days_with_temp'] >= 60]
    if yrs.empty:
        T.note(f'{labels[pick]} has no summer with 60 or more days of temperature readings yet.')
        st.stop()
    T.section('Days at or above 73°F, by year', 'Years with fewer than 60 summer readings are left out.')
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
        T.section(f'Daily water temperature, {year}')
        g = A._gauge(df, pick)
        g = g[g['year'] == year]
        fig = go.Figure()
        for a in v['runs_of_3_plus_days']:
            fig.add_vrect(x0=a['from'], x1=pd.Timestamp(a['to']) + pd.Timedelta(days=1),
                          fillcolor=T.HOT_BAND, line_width=0, layer='below')
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
                    f'<div class="scope">Scope: {T.esc(a["scope"])} · {T.esc(a["mode"])}</div>'
                    '</div>', unsafe_allow_html=True)
        for f in a['flags']:
            T.note(f)
        T.label('Findings')
        st.markdown(a['findings'].replace('$', r'\$').replace('\n', '  \n'))
        if a.get('interpretation'):
            T.label('Interpretation')
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
               f'USGS daily values for {df["site_no"].nunique()} gauges from water '
               'year 2001 on. A reading is the mean flow for one whole day, so the newest one is usually yesterday.')
    status_line()
    T.stats([('Daily rows', f'{len(df):,}', 'one per gauge per day'),
             ('Gauges', str(df['site_no'].nunique()), f"{len(recent_temp)} with recent water temp"),
             ('First reading', T.date(df['date'].min()), ''),
             ('Newest reading', T.date(LAST), ss.data_origin)])

    T.section('Data issues found', 'Anything odd the app found while loading. Nothing is dropped without a note here.')
    for n in notes:
        T.note(n['message'], ok=n['level'] == 'ok')
    quiet = sum(1 for s_ in order if s_ not in recent_flow)
    if quiet:
        T.note(f'{quiet} of {len(order)} gauges in {WHERE} have no flow reading in the last 3 days of the data. '
               'Seasonal gauges shut off in fall and winter. They show as no reading on the map.')
    if SNAP:
        st.caption(f"Snapshot: {SNAP.get('source', '')}. Downloaded "
                   f"{T.date(SNAP['downloaded']) if SNAP.get('downloaded') else 'date unknown'}. {SNAP.get('note', '')}")

    T.section('Get the latest from USGS',
             f'Pulls the last {config.REFRESH_DAYS} days, and every day since the snapshot, from the USGS '
             'Water Data API and lays it over the snapshot (USGS revises recent values).')
    c1, c2 = st.columns([1, 2])
    if c1.button('Refresh from USGS', type='primary'):
        try:
            with st.spinner('Asking USGS'):
                start = dp.refresh_start(SNAP.get('downloaded'), pd.Timestamp.today().date())
                fresh = fetch_recent(start, secret('USGS_API_KEY'), str(pd.Timestamp.now().floor('h')))
            merged = dp.merge_refresh(dp.read_csv(ss.daily_bytes), fresh)      # covers everything in recent_bytes
            buf = io.StringIO()
            merged.to_csv(buf, index=False)
            ss.daily_bytes = gzip.compress(buf.getvalue().encode(), 1)     # 10x less memory per visitor
            ss.recent_bytes = b''
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

    T.section('Upload changed data', 'Replaces just that table. Use this for the validation tests.')
    up = st.file_uploader('Daily values or sites file (CSV, or CSV.GZ)', type=['csv', 'gz'],
                          key=f'upload{ss.get("upload_n", 0)}')
    if up is not None:
        h = hashlib.md5(up.getvalue()).hexdigest()
        if ss.get('last_upload') != h:
            name = up.name.lower()
            if not any(k in name for k in config.FILES['sites'] + config.FILES['daily']):
                T.note('The file name must contain "daily" or "sites" so the app knows which table it replaces.',
                       error=True)
            elif any(k in name for k in config.FILES['sites']):
                ss.sites_bytes, ss.sites_src, ss.last_upload = up.getvalue(), f'Uploaded {up.name}', h
                st.rerun()
            else:
                ss.daily_bytes, ss.daily_src, ss.last_upload = up.getvalue(), f'Uploaded {up.name}', h
                ss.recent_bytes = b''
                ss.data_origin = f'uploaded file {up.name}'
                st.rerun()
    if st.button('Restore original data'):
        ss.daily_bytes = (ROOT / 'data' / 'daily_values.csv.gz').read_bytes()
        ss.sites_bytes = (ROOT / 'data' / 'sites.csv').read_bytes()
        ss.daily_src, ss.sites_src, ss.last_upload = SNAPSHOT_SRC, 'data/sites.csv', None
        ss.pop('csv_ready', None)
        ss.upload_n = ss.get('upload_n', 0) + 1
        st.rerun()
    tot = df['flow_cfs'].sum()
    st.caption(f'Check sum: total of all daily flows = {tot:,.0f} cfs-days. Sites from {ss.sites_src}.')

    T.section('Data quality by gauge',
             'Estimated days are mostly winter ice.')
    q = [{**row, 'first': T.date(row['first']), 'last': T.date(row['last'])} for row in quality_cached(DATA_KEY)]
    T.table(q, [('gauge', 'Gauge'), ('first', 'First'), ('last', 'Last'), ('missing_flow_days', 'Missing'),
                ('estimated_days', 'Estimated'), ('ice_days', 'Ice'),
                ('temp_days', 'Temp days')],
            num=('missing_flow_days', 'estimated_days', 'ice_days', 'temp_days'))
    # Building the CSV takes seconds, so it waits for a click instead of slowing every visit to this page
    want = (DATA_KEY, region)
    if ss.get('csv_ready') == want or st.button(f'Prepare daily data for {region} (CSV)'):
        ss.csv_ready = want
        st.download_button(f'Download daily data for {region} (CSV)', region_csv(DATA_KEY, region),
                           f"daily_values_{region.lower().replace(' ', '_')}.csv", 'text/csv')

T.colophon('Data: U.S. Geological Survey daily values (NWIS), refreshed through the USGS Water Data API. '
           'River lines: USGS NHDPlus via NLDI. Basemap: © OpenStreetMap contributors, © CARTO. Imagery: USGS The National Map. '
           'Land: BLM. Boat ramps: Montana FWP. '
           'USGS can revise recent values. Not a safety tool; check conditions and FWP rules before you go.')
