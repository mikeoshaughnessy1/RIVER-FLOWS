"""Looks only: colors, CSS, Plotly template and small HTML blocks. No math in here."""
import html
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

PAPER, INK, MUTED, RULE = '#f6f3ec', '#1c2326', '#6b7375', '#d9d2c3'
RIVER, RIVER_LIGHT, BAND = '#1d5c63', '#8fb5b3', '#d6e3df'
HOT, COLD = '#b4532a', '#3f6e9a'

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,650&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400&display=swap');
html, body, .stApp, [data-testid=stMarkdownContainer] p, [data-testid=stMarkdownContainer] li,
label, input, textarea, button {{ font-family: 'Inter', sans-serif; }}
[data-testid=stIconMaterial] {{ font-family: 'Material Symbols Rounded' !important; }}
h1, h2, h3, .rr-serif {{ font-family: 'Fraunces', Georgia, serif !important; color: {INK}; letter-spacing: -0.01em; }}
h1 *, h2 *, h3 * {{ font-family: inherit !important; }}
.block-container {{ padding-top: 3.6rem; max-width: 1180px; }}
.rr-mast {{ border-bottom: 2px solid {INK}; padding-bottom: .4rem; margin-bottom: 1.2rem; }}
.rr-mast .kicker {{ font: 600 .72rem 'Inter'; letter-spacing: .14em; text-transform: uppercase; color: {RIVER}; }}
.rr-mast .title {{ font: 650 2.3rem/1.05 'Fraunces', serif; color: {INK}; margin: .15rem 0; }}
.rr-mast .sub {{ color: {MUTED}; font-size: .92rem; }}
.rr-figure {{ font: 600 .72rem 'Inter'; letter-spacing: .12em; text-transform: uppercase; color: {MUTED};
             border-top: 1px solid {RULE}; padding-top: .55rem; margin: 1.4rem 0 .2rem; }}
.rr-figure b {{ color: {INK}; }}
.rr-cap {{ color: {MUTED}; font-size: .86rem; margin: -.2rem 0 .6rem; }}
.rr-table {{ width: 100%; border-collapse: collapse; font-size: .9rem; }}
.rr-table th {{ text-align: left; font: 600 .7rem 'Inter'; letter-spacing: .08em; text-transform: uppercase;
               color: {MUTED}; border-bottom: 1.5px solid {INK}; padding: .35rem .5rem; }}
.rr-table td, .rr-table th {{ border-left: none !important; border-right: none !important; border-top: none; }}
.rr-table {{ border: none !important; }}
.rr-table td {{ border-bottom: 1px solid {RULE}; padding: .45rem .5rem; vertical-align: top; }}
.rr-table td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
.rr-table tr.river td {{ padding-top: .9rem; font: 600 .74rem 'Inter'; letter-spacing: .1em;
                         text-transform: uppercase; color: {RIVER}; border-bottom: none; }}
.rr-pill {{ display: inline-block; padding: 0 .4rem; border-radius: 3px; font-size: .74rem; background: {BAND}; color: {RIVER}; }}
.rr-pill.hot {{ background: #f3dfd3; color: {HOT}; }}
.rr-pill.warn {{ background: #efe6cf; color: #7a5b12; }}
.rr-stats {{ display: grid; grid-template-columns: repeat(4, 1fr); border-top: 1px solid {INK}; border-bottom: 1px solid {RULE}; }}
.rr-stats > div {{ padding: .7rem .8rem; border-right: 1px solid {RULE}; }}
.rr-stats > div:last-child {{ border-right: none; }}
.rr-stats .k {{ font: 600 .68rem 'Inter'; letter-spacing: .1em; text-transform: uppercase; color: {MUTED}; }}
.rr-stats .v {{ font: 650 1.6rem 'Fraunces', serif; color: {INK}; }}
.rr-stats .s {{ color: {MUTED}; font-size: .8rem; }}
.rr-note {{ border-left: 3px solid #c9a227; background: #f1ead6; padding: .6rem .8rem; margin: .5rem 0; font-size: .9rem; }}
.rr-note.ok {{ border-color: {RIVER}; background: #e3ece8; }}
.rr-entry {{ border-top: 1px solid {RULE}; padding: 1rem 0 .4rem; }}
.rr-entry .q {{ font: italic 500 1.2rem 'Fraunces', serif; color: {INK}; }}
.rr-entry .lab {{ font: 600 .68rem 'Inter'; letter-spacing: .12em; text-transform: uppercase; color: {RIVER}; margin-top: .6rem; }}
.rr-colophon {{ border-top: 1px solid {RULE}; margin-top: 2.5rem; padding-top: .6rem; color: {MUTED}; font-size: .78rem; }}
section[data-testid=stSidebar] [data-testid=stRadio] label p {{ font-size: .95rem; }}
section[data-testid=stSidebar] [data-testid=stRadio] [data-testid=stRadioOption][data-selected=true] p {{ font-weight: 600; color: {RIVER}; }}
@media (max-width: 640px) {{
  .rr-stats {{ grid-template-columns: 1fr 1fr; }}
  .rr-stats > div:nth-child(2) {{ border-right: none; }}
  .rr-mast .title {{ font-size: 1.8rem; }}
  .rr-table {{ font-size: .82rem; }}
}}
</style>
"""

pio.templates['river'] = go.layout.Template(layout=dict(
    font=dict(family='Inter, sans-serif', size=12, color=INK),
    paper_bgcolor=PAPER, plot_bgcolor=PAPER, colorway=[RIVER, HOT, COLD, '#7d7a3a', '#6d5a8a'],
    xaxis=dict(showgrid=False, linecolor=INK, ticks='outside', tickcolor=RULE),
    yaxis=dict(gridcolor=RULE, zeroline=False, linecolor=PAPER),
    margin=dict(l=10, r=10, t=10, b=10), hoverlabel=dict(font_family='Inter'),
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


def note(msg, ok=False):
    st.markdown(f'<div class="rr-note{" ok" if ok else ""}">{esc(msg)}</div>', unsafe_allow_html=True)


def table(rows, cols, num=()):
    """rows: list of dicts. cols: list of (key, header). A row with '_group' renders as a group head."""
    head = ''.join(f'<th style="text-align:{"right" if k in num else "left"}">{esc(h)}</th>' for k, h in cols)
    body = ''
    for r in rows:
        if '_group' in r:
            body += f'<tr class="river"><td colspan="{len(cols)}">{esc(r["_group"])}</td></tr>'
            continue
        body += '<tr>' + ''.join(
            f'<td class="{"num" if k in num else ""}">{r.get(k, "") if str(k).endswith("_html") else esc(r.get(k, ""))}</td>'
            for k, _ in cols) + '</tr>'
    st.markdown(f'<table class="rr-table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>',
                unsafe_allow_html=True)


def colophon(text):
    st.markdown(f'<div class="rr-colophon">{esc(text)}</div>', unsafe_allow_html=True)


def cfs(x):
    return '–' if x is None else f'{x:,.0f}'
