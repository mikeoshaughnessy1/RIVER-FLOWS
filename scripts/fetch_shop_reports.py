"""Pull the newest fishing report from each local fly shop in data/shop_sources.csv into
data/shop_reports.json. Runs once a day from the refresh workflow.

Two kinds of source:
  page  a report page with a date under the 'Fishing Report' heading (River's Edge, Montana Angler)
  feed  an RSS or Atom feed; the newest post is the report (Sweetwater, Big Sky Anglers)
A shop that fails keeps its last saved report, so one broken site never blanks the rest.
"""
from __future__ import annotations
import csv
import datetime as dt
import email.utils
import json
import pathlib
import re
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

import requests

DATA = pathlib.Path(__file__).resolve().parent.parent / 'data'
UA = 'Mozilla/5.0 (compatible; RiverReport/1.0; student project; rockies-river-report.streamlit.app)'
EXCERPT_MIN, EXCERPT_MAX = 180, 340   # characters: two or three sentences
MIN_LINE = 40                         # shorter lines after the date are headings, bylines and flow notes
FLOW_RE = re.compile(r'\b(cfs|cubic feet)\b', re.I)

BLOCK = {'p', 'div', 'br', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'section', 'article', 'tr', 'header'}
SKIP = {'script', 'style', 'noscript', 'nav', 'footer', 'svg', 'form'}


class _Text(HTMLParser):
    """HTML to plain text, one line per block element."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP:
            self.skip += 1
        elif tag in BLOCK:
            self.out.append('\n')

    def handle_endtag(self, tag):
        if tag in SKIP and self.skip:
            self.skip -= 1
        elif tag in BLOCK:
            self.out.append('\n')

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def html_text(markup: str) -> str:
    p = _Text()
    p.feed(markup)
    lines = (re.sub(r'\s+', ' ', x).strip() for x in ''.join(p.out).split('\n'))
    return '\n'.join(x for x in lines if x)


MONTHS = 'Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec'
DATE_RE = re.compile(
    rf'(?P<iso>20\d\d-\d\d-\d\d)'
    rf'|(?P<mdy>\d{{1,2}})/(?P<d>\d{{1,2}})/(?P<y>(?:20)?\d\d)\b'
    rf'|(?P<mon>(?:{MONTHS})[a-z]*)\.?\s+(?P<md>\d{{1,2}})(?:st|nd|rd|th)?,?\s+(?P<my>20\d\d)')


def parse_date(m: re.Match) -> dt.date | None:
    try:
        if m['iso']:
            return dt.date.fromisoformat(m['iso'])
        if m['mdy']:
            y = int(m['y'])
            return dt.date(y + 2000 if y < 100 else y, int(m['mdy']), int(m['d']))
        return dt.datetime.strptime(f"{m['mon'][:3]} {m['md']} {m['my']}", '%b %d %Y').date()
    except ValueError:
        return None


def excerpt(text: str) -> str:
    """The shop's first real sentences: skip short heading and byline lines, stop near EXCERPT_MAX."""
    # headings, bylines, flow lines: short, or a title-length line with no closing punctuation
    heading = lambda x: len(x) < MIN_LINE or (len(x) < 2 * MIN_LINE and x[-1] not in '.!?:)"\u201d')
    lines = text.split('\n')
    while lines and heading(lines[0]):
        lines.pop(0)
    end = next((i for i, x in enumerate(lines) if heading(x)), len(lines))   # stop at the next section
    body = re.sub(r'^(current conditions|conditions|report|streamflow)\s*:\s*', '', ' '.join(lines[:end]), flags=re.I)
    out = ''
    for s in re.split(r'(?<=[.!?])\s+', body.strip()):
        if FLOW_RE.search(s):   # their flow numbers; the app shows live gauge flows
            continue
        if out and len(out) + len(s) > EXCERPT_MAX:
            break
        out = f'{out} {s}'.strip()
        if len(out) >= EXCERPT_MIN:
            break
    if len(out) > EXCERPT_MAX:   # one very long sentence
        out = out[:EXCERPT_MAX].rsplit(' ', 1)[0].rstrip(',;:') + '...'
    return out


def parse_page(markup: str) -> tuple[dt.date, str] | None:
    """Date and excerpt from a report page: the first date within a few lines of a
    'Fishing Report' heading, and the writing after it."""
    text = html_text(markup)
    for h in re.finditer(r'fishing report', text, re.I):
        m = DATE_RE.search(text, h.end(), h.end() + 80)
        if m and (d := parse_date(m)):
            body = excerpt(text[m.end():].lstrip(' ,.-:–'))
            if body:
                return d, body
    return None


def _local(tag):
    return tag.rsplit('}', 1)[-1]


def parse_feed(xml: str, section: str = '') -> tuple[dt.date, str, str] | None:
    """Date, link and excerpt of the newest post in an RSS or Atom feed. With `section`,
    the excerpt starts under the first line that begins with that heading."""
    root = ET.fromstring(xml)
    posts = []
    for item in root.iter():
        if _local(item.tag) not in ('item', 'entry'):
            continue
        f = {_local(c.tag): c for c in item}
        when = None
        stamp = next((f[k].text for k in ('pubDate', 'published', 'updated') if k in f and f[k].text), None)
        if stamp:
            when = (email.utils.parsedate_to_datetime(stamp) if 'pubDate' in f else dt.datetime.fromisoformat(stamp)).date()
        link = (f['link'].get('href') or f['link'].text or '') if 'link' in f else ''
        body = next((f[k].text for k in ('encoded', 'content', 'description', 'summary') if k in f and f[k].text), '')
        if when and body:
            posts.append((when, (link or '').strip(), body))
    if not posts:
        return None
    when, link, body = max(posts, key=lambda p: p[0])
    text = html_text(body)
    if section:
        lines = text.split('\n')
        at = next((i for i, x in enumerate(lines) if x.lower() == section.lower() or x.lower().startswith(section.lower() + ' ')), None)
        if at is not None:
            text = '\n'.join(lines[at + 1:])
    return when, link, excerpt(text)


def fetch_one(src: dict, get=requests.get) -> dict:
    r = get(src['url'], timeout=15, headers={'User-Agent': UA})
    r.raise_for_status()
    if src['kind'] == 'feed':
        got = parse_feed(r.text, src.get('section', ''))
        if not got:
            raise ValueError('no posts in feed')
        when, link, text = got
    else:
        got = parse_page(r.text)
        if not got:
            raise ValueError('no dated report found on page')
        (when, text), link = got, src['url']
    if not link.startswith('https://'):
        link = src['url']
    if not text:
        raise ValueError('report has no text')
    return {k: src[k] for k in ('shop', 'town', 'river', 'label')} | {
        'date': when.isoformat(), 'url': link, 'excerpt': text}


def main():
    out_path = DATA / 'shop_reports.json'
    try:
        old = {(r['shop'], r['label']): r for r in json.loads(out_path.read_text())['reports']}
    except (OSError, ValueError, KeyError):
        old = {}
    with open(DATA / 'shop_sources.csv', newline='') as f:
        sources = list(csv.DictReader(f))
    reports, failed = [], 0
    for src in sources:
        try:
            reports.append(fetch_one(src))
            print('ok  ', src['shop'], src['label'], reports[-1]['date'])
        except Exception as e:   # any one shop breaking must not stop the rest
            failed += 1
            print('FAIL', src['shop'], src['label'], type(e).__name__, str(e)[:120])
            if (src['shop'], src['label']) in old:
                reports.append(old[(src['shop'], src['label'])])
    out_path.write_text(json.dumps({'fetched': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
                                    'reports': reports}, indent=1) + '\n')
    print(f'{len(reports)} reports saved, {failed} sources failed')
    return 1 if failed == len(sources) else 0


if __name__ == '__main__':
    sys.exit(main())
