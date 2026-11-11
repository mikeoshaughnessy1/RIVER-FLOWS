import json
import pathlib
import sys
import analytics as A

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'scripts'))
import fetch_shop_reports as F   # noqa: E402

PAGE = """<html><nav>Fishing Reports 2020-01-01</nav><h2>Current Gallatin River Fishing Report</h2>
<p>2026-11-10</p><p>355 CFS @ Gallatin Gateway.</p>
<p>The Gallatin has been fishing awfully well these past few days. Flows have been very steady.</p>
<p>Fishing deeper buckets right now has been a safe bet. Midges in the afternoon. More text after that here.</p>
<script>var x = "Fishing Report 1/1/24";</script></html>"""

RSS = """<?xml version="1.0"?><rss xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>
<item><title>Old</title><link>https://shop.example/old</link><pubDate>Mon, 02 Nov 2026 22:12:23 +0000</pubDate>
<content:encoded><![CDATA[<p>Shop Fishing Report</p><p>By Max</p><h3>Yellowstone River</h3>
<p>The Yellowstone has been fishing well, and the rubberlegs keep producing over the past couple of weeks.</p>
<h3>Spring Creeks</h3><p>DePuy's has been fishing well.</p>]]></content:encoded></item>
<item><title>Older</title><link>https://shop.example/older</link><pubDate>Fri, 22 May 2026 15:13:56 +0000</pubDate>
<description>Runoff is here and the river is high and brown for now. Wait it out.</description></item>
</channel></rss>"""

ATOM = """<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Madison River Fishing Report - October 22, 2026</title>
<link href="https://bsa.example/r1"/><published>2026-10-22T05:30:01-06:00</published>
<content type="html">&lt;p&gt;West Yellowstone - 303 CFS.&lt;/p&gt;&lt;p&gt;Early fall flows and the fish are spread out. A little skinny, but the browns are moving.&lt;/p&gt;</content>
</entry></feed>"""


def test_page_takes_the_date_under_the_report_heading_not_nav_or_scripts():
    d, text = F.parse_page(PAGE)
    assert d.isoformat() == '2026-11-10'
    assert text.startswith('The Gallatin has been fishing awfully well')
    assert 'CFS' not in text and len(text) <= F.EXCERPT_MAX


def test_two_digit_years_and_long_dates_parse():
    assert F.parse_page('<h1>Gallatin River Fishing Report 10/23/26</h1><p>' + 'Late October fishing is here. ' * 3 + '</p>')[0].isoformat() == '2026-10-23'
    assert F.parse_page('<h1>Gallatin River Fishing Report</h1><p>Friday, November 6, 2026</p><p>Current Conditions: '
                        + 'We love the months of October and November on the Gallatin River. ' * 2 + '</p>')[1].startswith('We love')


def test_paragraph_missing_its_last_period_is_still_the_report():
    # regression: River's Edge Gallatin, 2026-11-10, lost its report to the river blurb below it
    page = ('<h2>Current Gallatin River Fishing Report</h2><p>2026-11-10</p><p>The Gallatin has been fishing awfully '
            'well these past few days. Nymphing or dredging a streamer has been a good tactic</p><p>GO-TO FLIES:</p>'
            '<p>Perhaps the most accessible river in the Bozeman area, the Gallatin offers year-round fishing.</p>')
    assert F.parse_page(page)[1].startswith('The Gallatin has been fishing awfully well')


def test_page_without_a_dated_report_is_none():
    assert F.parse_page('<h1>Fishing Report</h1><p>Call the shop for conditions.</p>') is None


def test_rss_newest_post_and_section():
    d, link, text = F.parse_feed(RSS, 'Yellowstone River')
    assert d.isoformat() == '2026-11-02' and link == 'https://shop.example/old'
    assert text.startswith('The Yellowstone has been fishing well') and 'DePuy' not in text


def test_atom_drops_their_flow_numbers():
    d, link, text = F.parse_feed(ATOM)
    assert d.isoformat() == '2026-10-22' and link == 'https://bsa.example/r1'
    assert 'CFS' not in text and text.startswith('Early fall flows')


def test_failed_shop_keeps_its_last_report(tmp_path, monkeypatch):
    (tmp_path / 'shop_sources.csv').write_text('shop,town,river,label,url,kind,section\n'
                                               'A,X,Gallatin,Gallatin,https://a.example,page,\n')
    saved = {'shop': 'A', 'town': 'X', 'river': 'Gallatin', 'label': 'Gallatin', 'date': '2026-11-01',
             'url': 'https://a.example', 'excerpt': 'Old words.'}
    (tmp_path / 'shop_reports.json').write_text(json.dumps({'reports': [saved]}))
    monkeypatch.setattr(F, 'DATA', tmp_path)
    monkeypatch.setattr(F, 'fetch_one', lambda src: (_ for _ in ()).throw(TimeoutError('down')))
    assert F.main() == 1
    assert json.loads((tmp_path / 'shop_reports.json').read_text())['reports'] == [saved]


REPORTS = [{'shop': 'A', 'river': 'Madison', 'label': 'Upper Madison', 'date': '2026-11-06', 'url': 'u', 'excerpt': 'x'},
           {'shop': 'B', 'river': 'Madison', 'label': 'Madison', 'date': '2026-11-10', 'url': 'u', 'excerpt': 'y'},
           {'shop': 'C', 'river': 'Madison', 'label': 'Madison', 'date': '2026-10-22', 'url': 'u', 'excerpt': 'z'}]


def test_shop_reports_fresh_only_newest_first():
    r = A.shop_reports(REPORTS, 'Madison', '2026-11-10')
    assert r.error is None and [x['shop'] for x in r.value] == ['B', 'A']   # C is 19 days old


def test_shop_reports_cutoff_is_ten_days_and_no_future_dates():
    assert [x['shop'] for x in A.shop_reports(REPORTS, 'Madison', '2026-11-16').value] == ['B', 'A']   # A is 10 days old
    assert [x['shop'] for x in A.shop_reports(REPORTS, 'Madison', '2026-11-17').value] == ['B']
    assert [x['shop'] for x in A.shop_reports(REPORTS, 'Madison', '2026-11-07').value] == ['A']


def test_shop_reports_unknown_river_is_an_error():
    r = A.shop_reports(REPORTS, 'Bighorn', '2026-11-10')
    assert r.value is None and 'No fly shop covers Bighorn' in r.error


def test_saved_reports_file_is_well_formed():
    rows = json.loads((pathlib.Path(A._DATA) / 'shop_reports.json').read_text())['reports']
    assert rows and all(r['url'].startswith('https://') and r['excerpt'] and r['river'] for r in rows)
