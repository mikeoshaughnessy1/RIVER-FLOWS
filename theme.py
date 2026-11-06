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
HOT, COLD = '#b4532a', '#3f6e9a'
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
.block-container {{ padding-top: 3.4rem; padding-bottom: 3rem; max-width: 1180px; }}

/* Focus: always visible for keyboard users */
:focus-visible, button:focus-visible, [role=radio]:focus-visible, input:focus-visible,
[data-baseweb=select] *:focus-visible {{ outline: 2px solid {PINE} !important; outline-offset: 2px !important; }}
a {{ color: {RIVER}; }}

/* Inputs and buttons share one look */
.stButton > button, .stDownloadButton > button, [data-testid=stBaseButton-secondary],
[data-testid=stBaseButton-primary] {{ border-radius: {RADIUS}; border: 1px solid {RULE}; background: {SURFACE};
  color: {INK}; font-weight: 500; min-height: 2.5rem; box-shadow: none; }}
.stButton > button:hover, .stDownloadButton > button:hover {{ border-color: {PINE}; color: {PINE}; }}
[data-testid=stBaseButton-primary] {{ background: {PINE} !important; border-color: {PINE} !important; color: #fff !important; }}
[data-testid=stBaseButton-primary]:hover {{ background: #24412f !important; color: #fff !important; }}
[data-baseweb=select] > div, [data-baseweb=input], .stDateInput input, [data-testid=stFileUploaderDropzone] {{
  border-radius: {RADIUS} !important; background: {SURFACE} !important; border-color: {RULE} !important; }}
[data-testid=stWidgetLabel] p {{ font-size: .8rem; font-weight: 600; color: {INK2}; letter-spacing: .01em; }}
[data-testid=stExpander] details {{ border-radius: {RADIUS}; border-color: {RULE}; background: {SURFACE}; }}
[data-testid=stCaptionContainer] {{ color: {MUTED}; }}

/* Sidebar */
section[data-testid=stSidebar] {{ background: #ede8dd; border-right: 1px solid {RULE}; }}
section[data-testid=stSidebar] [data-testid=stRadio] label {{ padding: .28rem 0; }}
section[data-testid=stSidebar] [data-testid=stRadio] label p {{ font-size: .95rem; }}
section[data-testid=stSidebar] [data-testid=stRadioOption][data-selected=true] p {{ font-weight: 600; color: {PINE}; }}
.rr-brand {{ font: 650 1.35rem 'Fraunces', serif; color: {INK}; }}
.rr-brand-sub {{ color: {MUTED}; font-size: .8rem; margin-bottom: .9rem; }}

/* Masthead and status line */
.rr-mast {{ padding-bottom: .55rem; margin-bottom: .2rem; }}
.rr-mast .kicker {{ font: 600 .72rem 'Inter'; letter-spacing: .14em; text-transform: uppercase; color: {PINE}; }}
.rr-mast .title {{ font: 650 2.25rem/1.08 'Fraunces', serif; color: {INK}; margin: .2rem 0 .3rem; }}
.rr-mast .sub {{ color: {INK2}; font-size: .95rem; max-width: 62ch; line-height: 1.5; }}
.rr-status {{ display: flex; flex-wrap: wrap; gap: .35rem 1.2rem; border-top: 2px solid {INK}; border-bottom: 1px solid {RULE};
  padding: .5rem 0; margin: .3rem 0 1.1rem; font-size: .82rem; color: {INK2}; }}
.rr-status b {{ color: {INK}; font-weight: 600; }}
.rr-status .warn {{ color: #7a4d00; }}
.rr-dot {{ display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: .35rem;
  vertical-align: middle; background: {PINE}; }}
.rr-dot.stale {{ background: #c9a227; }}

.rr-figure {{ font: 600 .72rem 'Inter'; letter-spacing: .12em; text-transform: uppercase; color: {MUTED};
             border-top: 1px solid {RULE}; padding-top: .6rem; margin: 1.6rem 0 .25rem; }}
.rr-figure b {{ color: {INK}; }}
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
.rr-pill.hot {{ background: #f3dfd3; color: #8f3a17; }}
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

/* Map legend and gauge card */
.rr-legend {{ display: flex; flex-wrap: wrap; align-items: center; gap: .5rem 1.4rem; padding: .7rem .85rem;
  background: {SURFACE}; border: 1px solid {RULE}; border-radius: {RADIUS} {RADIUS} 0 0; border-bottom: none; font-size: .84rem; }}
.rr-legend .what {{ flex: 1 1 260px; color: {INK2}; line-height: 1.4; }}
.rr-legend .what b {{ color: {INK}; }}
.rr-legend .ramp {{ flex: 0 1 230px; }}
.rr-legend .bar {{ height: 8px; border-radius: 4px; }}
.rr-legend .ticks {{ display: flex; justify-content: space-between; font-size: .72rem; color: {MUTED};
  font-variant-numeric: tabular-nums; margin-top: .15rem; }}
.rr-legend .keys {{ display: flex; flex-wrap: wrap; gap: .3rem .9rem; flex: 1 1 100%; }}
.rr-legend .key {{ white-space: nowrap; color: {INK2}; }}
.rr-sym {{ display: inline-block; width: 1.1rem; text-align: center; font-weight: 700; }}
.rr-mapframe {{ border: 1px solid {RULE}; border-top: none; border-radius: 0 0 {RADIUS} {RADIUS}; overflow: hidden; margin-bottom: .3rem; }}
.rr-card {{ background: {SURFACE}; border: 1px solid {RULE}; border-radius: {RADIUS}; padding: .8rem .95rem; margin: .4rem 0 .6rem; }}
.rr-card .name {{ font: 650 1.15rem 'Fraunces', serif; color: {INK}; }}
.rr-card .meta {{ color: {MUTED}; font-size: .8rem; margin-bottom: .45rem; }}
.rr-card .row {{ display: flex; flex-wrap: wrap; gap: .4rem 1.6rem; font-size: .9rem; color: {INK2}; }}
.rr-card .row b {{ color: {INK}; font-variant-numeric: tabular-nums; }}

.rr-entry {{ border-top: 1px solid {RULE}; padding: 1rem 0 .4rem; }}
.rr-entry .q {{ font: italic 500 1.2rem 'Fraunces', serif; color: {INK}; }}
.rr-entry .lab {{ font: 600 .68rem 'Inter'; letter-spacing: .12em; text-transform: uppercase; color: {PINE}; margin-top: .6rem; }}
.rr-colophon {{ border-top: 1px solid {RULE}; margin-top: 2.5rem; padding-top: .7rem; color: {MUTED}; font-size: .78rem; line-height: 1.5; }}

@media (max-width: 760px) {{
  .block-container {{ padding-left: 1rem; padding-right: 1rem; padding-top: 3rem; }}
  .rr-stats {{ grid-template-columns: 1fr 1fr; }}
  .rr-stats > div:nth-child(2) {{ border-right: none; }}
  .rr-stats > div:nth-child(-n+2) {{ border-bottom: 1px solid {RULE}; }}
  .rr-stats .v {{ font-size: 1.3rem; }}
  .rr-mast .title {{ font-size: 1.7rem; }}
  .rr-table {{ font-size: .84rem; }}
  .rr-legend .ramp {{ flex: 1 1 100%; }}
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
                f'<div class="title">{esc(title)}</div><div class="sub">{esc(sub)}</div></div>',
                unsafe_allow_html=True)


def figure(n, title, caption=None):
    st.markdown(f'<div class="rr-figure">Fig. {n} &nbsp;<b>{esc(title)}</b></div>', unsafe_allow_html=True)
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
    st.markdown(f'<div class="rr-status" role="status">{"".join(bits)}</div>', unsafe_allow_html=True)


def date(x, year=True):
    """One date format everywhere: 'Nov 4, 2026'."""
    import pandas as pd
    t = pd.Timestamp(x)
    return f'{t:%b} {t.day}, {t.year}' if year else f'{t:%b} {t.day}'


def table(rows, cols, num=()):
    """rows: list of dicts. cols: list of (key, header). A row with '_group' renders as a group head."""
    head = ''.join(f'<th style="text-align:{"right" if k in num else "left"}">{esc(h)}</th>' for k, h in cols)
    body = ''
    for r in rows:
        if '_group' in r:
            body += f'<tr class="river"><td colspan="{len(cols)}">{esc(r["_group"])}</td></tr>'
            continue
        body += '<tr>' + ''.join(
            f'<td class="{"num" if k in num else ("nowrap" if str(k).startswith("dir") else "")}">{r.get(k, "") if str(k).endswith("_html") else esc(r.get(k, ""))}</td>'
            for k, _ in cols) + '</tr>'
    st.markdown(f'<div class="rr-scroll"><table class="rr-table"><thead><tr>{head}</tr></thead>'
                f'<tbody>{body}</tbody></table></div>', unsafe_allow_html=True)


def colophon(text):
    st.markdown(f'<div class="rr-colophon">{esc(text)}</div>', unsafe_allow_html=True)


def cfs(x):
    return '–' if x is None else f'{x:,.0f}'


# ---- Map: diverging red (dropping / below normal) to blue (rising / above normal) ----
# Mid-gray neutral instead of a pale one so steady rivers stay visible on the light basemap.
DIVERGING = [(0.0, '#a51d2d'), (0.25, '#dd6650'), (0.5, '#9e998e'), (0.75, '#5b97cf'), (1.0, '#1c5aa6')]
OFF_SEASON = '#cfc9bc'


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
