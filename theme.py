"""Looks only: colors, CSS, Plotly template and small HTML blocks. No math in here."""
import html
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# ---- Design tokens: warm paper, pine, river, stone. Strong color is saved for data. ----
PAPER = '#f5f2eb'      # page
SURFACE = '#fbfaf6'    # cards, inputs
INK = '#1b2420'        # headings, numbers
INK2 = '#3b4542'       # body text
MUTED = '#5c6563'      # captions (5.4:1 on paper)
RULE = '#dcd5c6'       # hairlines
PINE = '#2e5140'       # interface accent: nav, buttons, focus
RIVER, RIVER_LIGHT, BAND = '#1d5c63', '#8fb5b3', '#d6e3df'
STONE = '#8c8577'
HOT, COLD, HOT_BAND = '#b4532a', '#3f6e9a', '#f3dfd3'
RADIUS = '6px'

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,650&family=Inter:wght@400;500;600&display=swap');
:root {{ --rr-pine: {PINE}; --rr-rule: {RULE}; --rr-surface: {SURFACE}; }}
html, body, .stApp, [data-testid=stMarkdownContainer] p, [data-testid=stMarkdownContainer] li,
label, input, textarea, button, select {{ font-family: 'Inter', system-ui, sans-serif; }}
.stApp {{ color: {INK2}; }}
[data-testid=stIconMaterial] {{ font-family: 'Material Symbols Rounded' !important; }}
h1, h2, h3, .rr-serif {{ font-family: 'Fraunces', Georgia, serif !important; color: {INK}; letter-spacing: -0.01em; }}
h1 *, h2 *, h3 * {{ font-family: inherit !important; }}
.block-container {{ padding-top: 1rem; padding-bottom: 3rem; max-width: 1200px; }}

/* Focus: always visible for keyboard users */
:focus-visible, button:focus-visible, [role=radio]:focus-visible, input:focus-visible {{ outline: 2px solid {PINE} !important; outline-offset: 2px !important; }}
.stSelectbox input:focus-visible, .stDateInput input:focus-visible {{ outline: none !important; }}   /* the box itself shows focus */
a {{ color: {RIVER}; }}

/* Inputs and buttons share one look */
.stButton > button, .stDownloadButton > button, [data-testid=stBaseButton-secondary],
[data-testid=stBaseButton-primary] {{ border-radius: {RADIUS}; border: 1px solid {RULE}; background: {SURFACE};
  color: {INK}; font-weight: 500; min-height: 2.5rem; box-shadow: none; }}
.stButton > button:hover, .stDownloadButton > button:hover {{ border-color: {PINE}; color: {PINE}; }}
[data-testid=stBaseButton-primary] {{ background: {PINE} !important; border-color: {PINE} !important; color: #fff !important; }}
[data-testid=stBaseButton-primary]:hover {{ background: #24412f !important; color: #fff !important; }}
[data-testid=stWidgetLabel] p {{ font-size: .8rem; font-weight: 600; color: {INK2}; letter-spacing: .01em; }}
[data-testid=stExpander] details {{ border-radius: {RADIUS}; border-color: {RULE}; background: {SURFACE}; }}
[data-testid=stCaptionContainer], [data-testid=stCaptionContainer] * {{ color: {MUTED}; opacity: 1; }}

/* Top bar and section tabs: the same on every screen, nothing hidden behind a drawer */
header[data-testid=stHeader] {{ background: transparent; height: 0; }}
.rr-brand {{ font: 650 1.45rem/1.15 'Fraunces', serif; color: {INK}; }}
.rr-brand-sub {{ color: {MUTED}; font-size: .8rem; }}
.st-key-nav {{ border-bottom: 1px solid {RULE}; margin-bottom: .5rem; overflow-x: auto; scrollbar-width: none; }}
.st-key-nav [role=radiogroup] {{ flex-wrap: nowrap; gap: 1.5rem; }}
.st-key-nav [data-testid=stRadioOption] {{ padding: .4rem 0 .5rem; border-bottom: 2px solid transparent; margin-bottom: -1px;
  cursor: pointer; white-space: nowrap; }}
.st-key-nav [data-testid=stRadioOption] > div > div:first-child:not([data-testid=stMarkdownContainer]) {{ display: none; }}
.st-key-nav [data-testid=stRadioOption] p {{ font-size: .95rem; font-weight: 500; color: {INK2}; }}
.st-key-nav [data-testid=stRadioOption]:hover p {{ color: {PINE}; }}
.st-key-nav [data-testid=stRadioOption][data-selected=true] {{ border-bottom-color: {PINE}; }}
.st-key-nav [data-testid=stRadioOption][data-selected=true] p {{ color: {PINE}; font-weight: 600; }}
.st-key-nav [data-testid=stRadioOption][data-focus-visible=true] {{ outline: 2px solid {PINE}; outline-offset: -2px; border-radius: 3px; }}

/* Masthead and status line */
.st-key-to_data button {{ border: none !important; background: none !important; min-height: 0; padding: 0; color: {MUTED}; }}
.st-key-to_data button p {{ font-size: .8rem; text-decoration: underline; }}
.st-key-to_data {{ margin-top: -.9rem; }}
.rr-mast {{ padding-bottom: .55rem; margin-bottom: .2rem; }}
.rr-mast .kicker {{ font: 600 .72rem 'Inter'; letter-spacing: .14em; text-transform: uppercase; color: {PINE}; }}
.rr-mast .title {{ font: 650 2.25rem/1.08 'Fraunces', serif; color: {INK}; margin: .15rem 0 .3rem; padding: 0; }}
.rr-mast .sub {{ color: {INK2}; font-size: .95rem; max-width: 88ch; line-height: 1.45; }}
.rr-status {{ display: flex; flex-wrap: wrap; gap: .35rem 1.2rem; border-top: 2px solid {INK}; border-bottom: 1px solid {RULE};
  padding: .5rem 0; margin: .3rem 0 1.1rem; font-size: .82rem; color: {INK2}; }}
.rr-status b {{ color: {INK}; font-weight: 600; }}
.rr-status .warn {{ color: #7a4d00; }}
.rr-dot {{ display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: .35rem;
  vertical-align: middle; background: {PINE}; }}
.rr-dot.stale {{ background: #c9a227; }}

.rr-section {{ font: 650 1.15rem/1.25 'Fraunces', serif !important; color: {INK} !important; border-top: 1px solid {RULE};
              padding: .7rem 0 0; margin: 1.6rem 0 .15rem; }}
.rr-cap {{ color: {MUTED}; font-size: .86rem; margin: -.1rem 0 .7rem; line-height: 1.45; }}

/* Tables scroll sideways on a phone instead of squeezing */
.rr-scroll {{ overflow-x: auto; -webkit-overflow-scrolling: touch; margin-bottom: .4rem; }}
.rr-table {{ width: 100%; border-collapse: collapse; font-size: .9rem; min-width: 560px; }}
.rr-table th {{ text-align: left; font: 600 .7rem 'Inter'; letter-spacing: .08em; text-transform: uppercase;
               color: {MUTED}; border-bottom: 1.5px solid {INK}; padding: .4rem .5rem; white-space: nowrap; }}
.rr-table td, .rr-table th {{ border-left: none !important; border-right: none !important; border-top: none; }}
.rr-table {{ border: none !important; }}
.rr-table td {{ border-bottom: 1px solid {RULE}; padding: .45rem .5rem; vertical-align: top; color: {INK2}; }}
.rr-table td.nowrap {{ white-space: nowrap; }}
.rr-table td.num {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; color: {INK}; }}
.rr-table tr.river td {{ padding-top: .95rem; font: 600 .72rem 'Inter'; letter-spacing: .1em;
                         text-transform: uppercase; color: {PINE}; border-bottom: none; }}
.rr-pill {{ display: inline-block; padding: 0 .45rem; border-radius: 999px; font-size: .74rem; background: {BAND}; color: {RIVER}; white-space: nowrap; }}
.rr-pill.low {{ background: #f6e1da; color: #84211f; }}
.rr-pill.high {{ background: #dce8f4; color: #17477f; }}
.rr-pill.warn {{ background: #efe6cf; color: #6d5410; }}

.rr-stats {{ display: grid; grid-template-columns: repeat(4, 1fr); border-top: 1px solid {INK}; border-bottom: 1px solid {RULE}; margin: .2rem 0 .4rem; }}
.rr-stats > div {{ padding: .75rem .85rem; border-right: 1px solid {RULE}; min-width: 0; }}
.rr-stats > div:last-child {{ border-right: none; }}
.rr-stats .k {{ font: 600 .68rem 'Inter'; letter-spacing: .1em; text-transform: uppercase; color: {MUTED}; }}
.rr-stats .v {{ font: 650 1.55rem 'Fraunces', serif; color: {INK}; font-variant-numeric: tabular-nums; }}
.rr-stats .s {{ color: {MUTED}; font-size: .8rem; overflow-wrap: anywhere; }}

.rr-note {{ border-left: 3px solid #c9a227; background: #f1ead6; padding: .65rem .85rem; margin: .5rem 0;
  font-size: .9rem; border-radius: 0 {RADIUS} {RADIUS} 0; color: {INK}; }}
.rr-note.ok {{ border-color: {PINE}; background: #e3ebe5; }}
.rr-note.err {{ border-color: #a51d2d; background: #f6e3df; }}

/* Map legend and gauge card. The map runs wider than the text but stops short of the screen
   edge: those side margins are where you scroll the page without grabbing the map. */
.st-key-mapbox {{ position: relative; width: calc(100vw - 7rem) !important; max-width: 1640px;
  left: 50%; transform: translateX(-50%); }}
.st-key-mapbox {{ border: 1px solid {RULE}; border-radius: {RADIUS}; overflow: hidden; background: {SURFACE}; }}
.st-key-mapbox [data-testid=stElementContainer] {{ margin: 0; }}
.st-key-mapbox [data-testid=stMarkdownContainer] {{ margin-bottom: 0; }}
.rr-legend {{ position: absolute; z-index: 3; top: 3rem; right: .7rem; width: 245px; display: flex; flex-wrap: wrap;
  gap: .4rem 1rem; padding: .65rem .8rem; background: {SURFACE}; border: 1px solid {RULE}; border-radius: {RADIUS};
  font-size: .8rem; pointer-events: none; }}
.rr-legend .what {{ flex: 1 1 100%; color: {INK2}; line-height: 1.4; }}
.rr-legend .what b {{ color: {INK}; }}
.rr-legend .ramp {{ flex: 1 1 100%; }}
.rr-legend .bar {{ height: 8px; border-radius: 4px; }}
.rr-legend .ticks {{ display: flex; justify-content: space-between; font-size: .72rem; color: {MUTED};
  font-variant-numeric: tabular-nums; margin-top: .15rem; }}
.rr-legend .keys {{ display: flex; flex-wrap: wrap; gap: .3rem .9rem; flex: 1 1 100%; }}
.rr-legend .key {{ white-space: nowrap; color: {INK2}; }}
.rr-sym {{ display: inline-block; width: 1.1rem; text-align: center; font-weight: 700; }}
.rr-spark {{ display: block; width: 100%; height: 44px; margin: .5rem 0 .15rem; }}
.rr-sparkcap {{ color: {MUTED}; font-size: .72rem; margin-bottom: .4rem; }}
.rr-tag {{ font: 500 .68rem 'Inter', sans-serif; color: {MUTED}; border: 1px solid {RULE}; border-radius: 999px; padding: .05rem .45rem; margin-left: .45rem; vertical-align: middle; }}
.rr-tempguide {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: .4rem; margin: .4rem 0 1rem; }}
.rr-tempguide div {{ background: {SURFACE}; border: 1px solid {RULE}; border-top: 4px solid var(--c); border-radius: {RADIUS}; padding: .5rem .65rem; font-size: .8rem; color: {INK2}; }}
.rr-tempguide div.now {{ outline: 2px solid {INK}; }}
.rr-tempguide b {{ display: block; color: {INK}; font-size: .9rem; }}
.rr-trend {{ color: {MUTED}; font-weight: 700; }}
.rr-rcard .line span:last-child {{ white-space: nowrap; flex: none; }}
.rr-card {{ background: {SURFACE}; border: 1px solid {RULE}; border-radius: {RADIUS}; padding: .8rem .95rem; margin: .4rem 0 .6rem; }}
.rr-card .name {{ font: 650 1.15rem 'Fraunces', serif; color: {INK}; }}
.rr-card .meta {{ color: {MUTED}; font-size: .8rem; margin-bottom: .45rem; }}
.rr-card .row {{ display: flex; flex-wrap: wrap; gap: .4rem 1.6rem; font-size: .9rem; color: {INK2}; }}
.rr-card .row b {{ color: {INK}; font-variant-numeric: tabular-nums; }}

.rr-rcards {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: .7rem; margin: .5rem 0 1rem; }}
.rr-rcard {{ background: {SURFACE}; border: 1px solid {RULE}; border-radius: {RADIUS}; padding: .7rem .85rem; }}
.rr-rcard .name {{ font: 650 1.05rem 'Fraunces', serif; color: {INK}; }}
.rr-rcard .say {{ color: {MUTED}; font-size: .8rem; margin: .1rem 0 .4rem; min-height: 1.1rem; }}
.rr-rcard .line {{ display: flex; justify-content: space-between; gap: .6rem; font-size: .85rem; padding: .22rem 0;
  border-top: 1px solid {RULE}; color: {INK2}; }}
.rr-rcard .line b {{ color: {INK}; font-variant-numeric: tabular-nums; white-space: nowrap; font-weight: 600; }}
.rr-group {{ font: 600 .72rem 'Inter'; letter-spacing: .1em; text-transform: uppercase; color: {PINE}; margin-top: 1rem; }}

.rr-entry {{ border-top: 1px solid {RULE}; padding: 1rem 0 .4rem; }}
.rr-entry .q {{ font: italic 500 1.2rem 'Fraunces', serif; color: {INK}; }}
.rr-entry .scope {{ color: {MUTED}; font-size: .8rem; }}
.rr-lab {{ font: 600 .68rem 'Inter'; letter-spacing: .12em; text-transform: uppercase; color: {PINE}; margin-top: .6rem; }}
.rr-colophon {{ border-top: 1px solid {RULE}; margin-top: 2.5rem; padding-top: .7rem; color: {MUTED}; font-size: .78rem; line-height: 1.5; }}

.maplibregl-ctrl-attrib {{ font-size: 10px; line-height: 1.3; }}
@media (max-width: 760px) {{
  .block-container {{ padding-left: 1rem; padding-right: 1rem; padding-top: 1rem; }}
  .st-key-nav [role=radiogroup] {{ gap: .8rem; }}
  .st-key-nav [data-testid=stRadioOption] p {{ font-size: .88rem; }}
  .st-key-map_mode [role=radiogroup] {{ gap: .5rem; flex-wrap: nowrap; }}
  .st-key-map_mode p {{ font-size: .88rem; white-space: nowrap; }}
  .st-key-controls [data-testid=stHorizontalBlock] {{ flex-wrap: wrap; gap: .5rem 1rem; }}
  .st-key-controls [data-testid=stColumn] {{ flex: 1 1 calc(50% - .5rem) !important; min-width: calc(50% - .5rem) !important; width: auto !important; }}
  .rr-stats {{ grid-template-columns: 1fr 1fr; }}
  .rr-stats > div:nth-child(2) {{ border-right: none; }}
  .rr-stats > div:nth-child(-n+2) {{ border-bottom: 1px solid {RULE}; }}
  .rr-stats .v {{ font-size: 1.3rem; }}
  .rr-mast .title {{ font-size: 1.7rem; }}
  .rr-table {{ font-size: .84rem; }}
  .st-key-topbar {{ flex-wrap: nowrap !important; align-items: center; }}
  .st-key-topbar .rr-brand-sub, .st-key-region label {{ display: none; }}
  .st-key-region {{ width: 150px !important; flex: 0 0 150px; }}
  .rr-mast .sub {{ font-size: .86rem; }}
  .rr-status > span:nth-child(n+2) {{ display: none; }}
  .st-key-mapbox {{ width: calc(100vw - 3.5rem) !important; }}
  .st-key-mapbox [data-testid=stVerticalBlock] {{ display: flex; flex-direction: column; }}
  .st-key-mapbox [data-testid=stElementContainer]:first-child {{ order: 2; }}
  .rr-legend {{ position: static; width: auto; border: none; border-top: 1px solid {RULE}; border-radius: 0; }}
}}
@media (prefers-reduced-motion: reduce) {{ * {{ transition: none !important; animation: none !important; }} }}
</style>
"""

pio.templates['river'] = go.layout.Template(layout=dict(
    font=dict(family='Inter, sans-serif', size=12.5, color=INK2),
    paper_bgcolor=PAPER, plot_bgcolor=PAPER, colorway=[RIVER, HOT, COLD, '#7d7a3a', '#6d5a8a'],
    xaxis=dict(showgrid=False, linecolor=INK2, ticks='outside', tickcolor=RULE, tickfont=dict(color=INK2)),
    yaxis=dict(gridcolor=RULE, zeroline=False, linecolor=PAPER, tickformat=',', tickfont=dict(color=INK2)),
    margin=dict(l=10, r=10, t=10, b=10),
    hoverlabel=dict(font_family='Inter', bgcolor=SURFACE, bordercolor=RULE, font=dict(color=INK)),
    legend=dict(orientation='h', y=1.08, x=0, bgcolor='rgba(0,0,0,0)'),
))
pio.templates.default = 'river'


def esc(x):
    return html.escape(str(x))


def inject():
    st.markdown(CSS, unsafe_allow_html=True)


def masthead(kicker, title, sub):
    st.markdown(f'<div class="rr-mast"><div class="kicker">{esc(kicker)}</div>'
                f'<h1 class="title">{esc(title)}</h1><div class="sub">{esc(sub)}</div></div>',
                unsafe_allow_html=True)


def brand(name, sub):
    st.markdown(f'<div class="rr-brand">{esc(name)}</div><div class="rr-brand-sub">{esc(sub)}</div>',
                unsafe_allow_html=True)


def label(text):
    st.markdown(f'<div class="rr-lab">{esc(text)}</div>', unsafe_allow_html=True)


def section(title, caption=None):
    st.markdown(f'<h2 class="rr-section">{esc(title)}</h2>', unsafe_allow_html=True)
    if caption:
        st.markdown(f'<div class="rr-cap">{esc(caption)}</div>', unsafe_allow_html=True)


def stats(items):
    cells = ''.join(f'<div><div class="k">{esc(k)}</div><div class="v">{esc(v)}</div>'
                    f'<div class="s">{esc(s)}</div></div>' for k, v, s in items)
    st.markdown(f'<div class="rr-stats">{cells}</div>', unsafe_allow_html=True)


def note(msg, ok=False, error=False):
    cls = ' ok' if ok else (' err' if error else '')
    role = 'alert' if error else 'status'
    st.markdown(f'<div class="rr-note{cls}" role="{role}">{esc(msg)}</div>', unsafe_allow_html=True)


def status(parts, stale=False):
    """One line under the masthead: what the newest reading is and how the data got here.
    parts: list of (label, value) or plain strings."""
    bits = []
    for i, p in enumerate(parts):
        if isinstance(p, tuple):
            bits.append(f'<span>{esc(p[0])} <b>{esc(p[1])}</b></span>')
        else:
            bits.append(f'<span class="{"warn" if stale and i == len(parts) - 1 else ""}">{esc(p)}</span>')
    dot = f'<span class="rr-dot{" stale" if stale else ""}" aria-hidden="true"></span>'
    if bits:
        bits[0] = bits[0].replace('<span>', f'<span>{dot}', 1).replace('<span class="">', f'<span>{dot}', 1)
    st.markdown(f'<div class="rr-status">{"".join(bits)}</div>', unsafe_allow_html=True)


def date(x, year=True):
    """One date format everywhere: 'Nov 4, 2026'."""
    import pandas as pd
    t = pd.Timestamp(x)
    return f'{t:%b} {t.day}, {t.year}' if year else f'{t:%b} {t.day}'


def table(rows, cols, num=()):
    """rows: list of dicts. cols: list of (key, header). A row with '_group' renders as a group head."""
    head = ''.join(f'<th scope="col" style="text-align:{"right" if k in num else "left"}">{esc(h)}</th>' for k, h in cols)
    body = ''
    for r in rows:
        if '_group' in r:
            body += f'<tr class="river"><td colspan="{len(cols)}">{esc(r["_group"])}</td></tr>'
            continue
        body += '<tr>' + ''.join(
            f'<td class="{"num" if k in num else ("nowrap" if str(k).startswith("dir") else "")}">{r.get(k, "") if str(k).endswith("_html") else esc(r.get(k, ""))}</td>'
            for k, _ in cols) + '</tr>'
    st.markdown(f'<div class="rr-scroll" tabindex="0" role="region" aria-label="Scrollable table"><table class="rr-table"><thead><tr>{head}</tr></thead>'
                f'<tbody>{body}</tbody></table></div>', unsafe_allow_html=True)


def river_cards(cards):
    """cards: list of dicts with name, say, and lines of (gauge, flow text, pill or date html)."""
    body = ''
    for c in cards:
        lines = ''.join(f'<div class="line"><span>{esc(g)}</span><span><b>{esc(f)}</b> {extra}</span></div>'
                        for g, f, extra in c['lines'])
        tag = f'<span class="rr-tag">{esc(c["tag"])}</span>' if c.get('tag') else ''
        body += (f'<div class="rr-rcard"><div class="name">{esc(c["name"])}{tag}</div><div class="say">{esc(c["say"])}</div>'
                 f'{c.get("spark", "")}{lines}</div>')
    st.markdown(f'<div class="rr-rcards">{body}</div>', unsafe_allow_html=True)


def sparkline(flows, normals, gauge):
    """30 days of flow against normal for the date, as a small inline chart."""
    w, h, pad = 240, 44, 4
    known = [n for n in normals if n == n]
    lo, hi = min(flows + known), max(flows + known)
    y = lambda v: h - pad - (v - lo) / ((hi - lo) or 1) * (h - 2 * pad)
    x = lambda i: i * w / (len(flows) - 1)
    path = lambda vals: ' '.join(f'{x(i):.1f},{y(v):.1f}' for i, v in enumerate(vals) if v == v)
    say = f'{gauge}: {flows[0]:,.0f} to {flows[-1]:,.0f} cfs over the last 30 days. Normal now {known[-1]:,.0f} cfs.' \
        if known else f'{gauge}: {flows[0]:,.0f} to {flows[-1]:,.0f} cfs over the last 30 days.'
    return (f'<svg class="rr-spark" viewBox="0 0 {w} {h}" preserveAspectRatio="none" role="img" aria-label="{esc(say)}">'
            f'<title>{esc(say)}</title>'
            f'<polyline points="{path(normals)}" fill="none" stroke="{MUTED}" stroke-width="1.25" stroke-dasharray="3 3" vector-effect="non-scaling-stroke"/>'
            f'<polyline points="{path(flows)}" fill="none" stroke="{PINE}" stroke-width="2" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>'
            f'</svg><div class="rr-sparkcap">30 days at {esc(gauge)}. Dashed is normal.</div>')


def temp_guide(bands, now=None):
    """What each water temperature means for trout, with the band `now` falls in outlined."""
    colors = ['#5b8fa8', '#7fb3a6', PINE, '#d9a441', '#b4532a']
    body = ''
    for (lo, hi, name, says), c in zip(bands, colors):
        here = now is not None and lo <= now < hi
        span = f'Under {hi}°F' if lo == 32 else f'{lo}°F and up' if hi == 100 else f'{lo} to {hi - 1}°F'
        body += (f'<div class="{"now" if here else ""}" style="--c:{c}"><b>{esc(name)}</b>{span}'
                 f'{f" · now {now:.0f}°F" if here else ""}<br>{esc(says)}</div>')
    st.markdown(f'<div class="rr-tempguide">{body}</div>', unsafe_allow_html=True)


def group(text):
    st.markdown(f'<div class="rr-group">{esc(text)}</div>', unsafe_allow_html=True)


def colophon(text):
    st.markdown(f'<div class="rr-colophon">{esc(text)}</div>', unsafe_allow_html=True)


def cfs(x):
    return '–' if x is None else f'{x:,.0f}'


# ---- Map: diverging red (dropping / below normal) to blue (rising / above normal) ----
# Mid-gray neutral instead of a pale one so steady rivers stay visible on the light basemap.
# Checked for red-green colorblindness: neighbors stay 11+ apart (delta E), all 3:1 on the page.
DROP, STEADY, RISE = '#9b1c2e', '#8a8983', '#17509e'
# Smooth heat map ramp, vivid for the dark imagery: green is no change. Not colorblind safe, so dots also carry + and -
DIVERGING = [(0.0, '#e6002e'), (0.2, '#ff5a00'), (0.38, '#ffd000'), (0.5, '#2fe38a'), (0.62, '#00d0ff'), (0.8, '#0090ff'), (1.0, '#1a2cff')]
OFF_SEASON = '#8f8b82'


# The map won't start until its style loads, so the app fetches CARTO's style itself and hands
# it over. A failed tile then only loses the background. BLANK_MAP is for when the style can't load.
STYLE_URL = 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json'
IMAGERY_TILES = 'https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}'
BLANK_MAP = {'version': 8, 'id': 'blank', 'sources': {}, 'glyphs': 'https://tiles.basemaps.cartocdn.com/fonts/{fontstack}/{range}.pbf',
             'layers': [{'id': 'paper', 'type': 'background', 'paint': {'background-color': '#f6f6f3'}}]}


LAND_TILES = ('https://gis.blm.gov/arcgis/rest/services/lands/BLM_Natl_SMA_Cached_without_PriUnk/'
              'MapServer/tile/{z}/{y}/{x}')


def with_imagery(style):
    """The light style with USGS satellite imagery under the roads and names, and clear state lines."""
    at = next(i for i, x in enumerate(style['layers']) if x['id'] == 'boundary_county')
    layer = {'id': 'imagery', 'type': 'raster', 'source': 'imagery'}    # true color: no paint adjustments
    lines = {'line-color': '#ffffff', 'line-width': 1.6, 'line-opacity': .85}
    names = {'text-color': '#ffffff', 'text-halo-color': 'rgba(0,0,0,.65)', 'text-halo-width': 1.2}
    top = []
    for x in style['layers'][at:]:
        if x['id'] in ('boundary_state', 'boundary_country_inner'):
            x = {k: v for k, v in {**x, 'paint': lines}.items() if k != 'minzoom'}
            if x['id'] == 'boundary_state':     # the stock filter hides state lines below zoom 6
                x['filter'] = ['==', ['get', 'kind_detail'], 4]
        elif x['type'] == 'symbol':
            x = {**x, 'paint': {**x.get('paint', {}), **names}}
        if x['id'] not in ('water', 'water_shadow', 'boundary_county'):
            top.append(x)
    return {**style, 'layers': style['layers'][:at] + [layer] + top,
            'sources': {**style['sources'], 'imagery': {'type': 'raster', 'tiles': [IMAGERY_TILES], 'tileSize': 256,
                                                        'maxzoom': 16, 'attribution': 'USGS The National Map'}}}


def with_land(style, before):
    """The style with BLM land tiles added under the town names. Plotly's own map layers failed here."""
    at = next((i for i, x in enumerate(style['layers']) if x['id'] == before), len(style['layers']))
    layer = {'id': 'land', 'type': 'raster', 'source': 'land', 'paint': {'raster-opacity': .45}}
    return {**style, 'id': style['id'] + '-land', 'layers': style['layers'][:at] + [layer] + style['layers'][at:],
            'sources': {**style['sources'], 'land': {'type': 'raster', 'tiles': [LAND_TILES], 'tileSize': 256,
                                                     'attribution': 'BLM'}}}


def ramp_css():
    return 'linear-gradient(90deg,' + ','.join(f'{c} {t * 100:.0f}%' for t, c in DIVERGING) + ')'


def _hex(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def diverging_color(t: float) -> str:
    """t in [0, 1]; 0 = full red, 0.5 = neutral, 1 = full blue."""
    t = min(1.0, max(0.0, t))
    for (a, ca), (b, cb) in zip(DIVERGING, DIVERGING[1:]):
        if t <= b:
            f = (t - a) / (b - a)
            x, y = _hex(ca), _hex(cb)
            return '#%02x%02x%02x' % tuple(round(x[i] + (y[i] - x[i]) * f) for i in range(3))
    return DIVERGING[-1][1]
