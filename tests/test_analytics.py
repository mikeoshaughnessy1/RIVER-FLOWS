import pandas as pd
import pytest
import analytics as A
import agent
import data_prep as dp
from conftest import make


def test_flow_stats_by_hand(tiny):
    r = A.flow_stats(tiny, '00000001', '2021-06-01', '2021-06-03')
    assert r.error is None
    assert r.value['mean_cfs'] == 410          # (400+410+420)/3
    assert r.value['max_cfs'] == 420 and r.value['max_date'] == '2021-06-03'
    assert round(r.value['volume_acre_ft'], 2) == round(1230 * 1.9835, 2)


def test_compare_to_normal_by_hand(tiny):
    r = A.compare_to_normal(tiny, '00000001', '2021-06-01', '2021-06-03')
    # other years: 2019 mean 110, 2020 mean 210 -> median 160; 410/160 = 256.25%
    assert r.value['median_of_other_years_cfs'] == 160
    assert round(r.value['pct_of_median'], 2) == 256.25
    assert r.value['rank'].startswith('1 of 3')
    assert any('comparable year' in c for c in r.caveats)   # only 2 years -> shaky normal flagged


def test_unknown_gauge_is_an_error_not_a_guess(tiny):
    r = A.flow_stats(tiny, 'Gallatin River')
    assert r.error and 'not found' in r.error and r.value is None


def test_label_lookup_is_case_insensitive(tiny):
    assert A.flow_stats(tiny, 'test nr town').error is None


def test_bad_dates(tiny):
    assert 'after' in A.flow_stats(tiny, '00000001', '2021-06-03', '2021-06-01').error
    assert 'No data in that window' in A.flow_stats(tiny, '00000001', '1990-01-01', '1990-02-01').error


def test_current_conditions_percent_of_median(tiny):
    r = A.current_conditions(tiny, ['00000001'])
    row = r.value[0]
    assert row['date'] == '2021-06-03' and row['flow_cfs'] == 420
    assert row['median_cfs'] == 170            # median of 120 and 220
    assert row['percentile'] == 100.0


def test_hot_water_runs():
    rows = [('00000001', f'2025-07-{d:02d}', 300, t) for d, t in
            [(1, 23.0), (2, 23.0), (3, 23.0), (4, 20.0), (5, 23.0), (6, 23.0), (8, 23.0)]]
    df, _, _ = make(rows)
    r = A.hot_water_days(df, '00000001', 2025)       # 23 C = 73.4 F
    assert r.value['days_at_or_above'] == 6
    # Jul 1-3 is a 3-day run; Jul 5-6 is only 2; Jul 8 is not consecutive with Jul 6
    assert r.value['runs_of_3_plus_days'] == [{'from': '2025-07-01', 'to': '2025-07-03', 'days': 3}]


def test_no_temp_sensor_message(tiny):
    r = A.hot_water_days(tiny, '00000002', 2021)
    assert 'no temperature sensor' in r.error


def test_partial_water_year_flagged(tiny):
    r = A.annual_peaks(tiny, '00000001')
    assert any('Partial water year' in c for c in r.caveats)


def test_messy_upload_does_not_crash():
    rows = [('6043500', '2025-06-01', 100, 10), ('00000001', 'not a date', 5, 10),
            ('00000001', '2025-06-02', 'ICE', 10), ('00000001', '2025-06-03', -5, 10),
            ('00000001', '2025-06-03', 300, 10)]
    df, _, notes = make(rows)
    msgs = ' '.join(n['message'] for n in notes)
    assert 'unreadable date' in msgs and 'non-numeric' in msgs and 'negative' in msgs and 'duplicate' in msgs
    assert '06043500' in set(df['site_no'])          # leading zero restored
    assert 'not in the sites file' in msgs           # unknown gauge kept, labelled by number
    assert df.loc[df['date'] == '2025-06-03', 'flow_cfs'].iloc[0] == 300   # kept the last duplicate


def test_missing_required_column():
    import data_prep as dp
    import pytest
    with pytest.raises(ValueError, match='missing required'):
        dp.build(pd.DataFrame({'site_no': ['1'], 'date': ['2025-01-01']}),
                 pd.DataFrame({'site_no': ['1'], 'site_name': ['x']}))


# ---- regression tests for bugs found while building ----

def test_the_gallatin_is_not_east_gallatin(real):
    """'the gallatin' contains 'e gallatin'; aliases must match whole words."""
    df, _ = real
    assert agent.find_gauges('How is the Gallatin running?', df)[0] == ['06043500']
    assert agent.find_gauges('How is the East Gallatin?', df)[0] == ['06048650']


def test_rules_routes(real):
    df, _ = real
    cases = {
        'Hot water days at Logan in 2021': ('hot_water_days', {'site': '06052500', 'year': 2021}),
        'Is runoff coming earlier on the Yellowstone?': ('runoff_timing_trend', {'site': '06192500'}),
        'How many days was the Jefferson below 500 cfs in 2025?':
            ('low_flow_days', {'site': '06036650', 'year': 2025, 'threshold_cfs': 500.0}),
        'Is the data clean?': ('data_quality_report', {}),
        'flows at $3 bridge': ('current_conditions', {'sites': ['06040000']}),
    }
    for q, (tool, args) in cases.items():
        assert agent.rules_route(q, df)[:2] == (tool, args), q


def test_flags(real):
    assert any('Forecast' in f for f in agent.question_flags('Will the Madison be fishable next week?'))
    assert any('Safety' in f for f in agent.question_flags('Is it safe to float the lower Madison?'))
    assert any('Rules' in f for f in agent.question_flags('Is there a hoot owl on the Jefferson?'))


def test_flow_change_by_hand():
    rows = [('00000001', f'2025-06-{d:02d}', f, 10) for d, f in [(1, 100), (8, 150), (9, 75)]]
    df, _, _ = make(rows)
    r = A.flow_change(df, '2025-06-08', 7, ['00000001'])
    assert r.value[0]['change_pct'] == 50 and r.value[0]['start_date'] == '2025-06-01'
    r = A.flow_change(df, '2025-06-09', 1, ['00000001'])
    assert r.value[0]['change_pct'] == -50


def test_flow_change_skips_gauges_with_no_recent_flow():
    rows = [('00000001', '2025-06-01', 100, 10), ('00000001', '2025-06-08', 120, 10),
            ('00000002', '2025-05-01', 50, 10)]
    df, _, _ = make(rows)
    r = A.flow_change(df, '2025-06-08', 7)
    assert [x['site_no'] for x in r.value] == ['00000001']
    assert any('No flow near' in c for c in r.caveats)


def test_flow_change_bad_window(tiny):
    assert A.flow_change(tiny, None, 0).error


def test_what_rivers_are_dropping_routes_to_change(real):
    """'what rivers' used to hit the list-gauges rule first."""
    df, _ = real
    assert agent.rules_route('What rivers are dropping this week?', df)[:2] == ('flow_change', {'window_days': 7})


def test_gauge_with_one_year_has_no_normal_but_no_crash():
    df, _, _ = make([('00000001', '2025-06-01', 100, 10), ('00000001', '2025-06-08', 120, 10)])
    r = A.current_conditions(df)
    assert r.error is None and r.value[0]['median_cfs'] is None


def test_no_percent_change_on_a_trickle():
    df, _, _ = make([('00000001', '2025-06-01', 0.3, 10), ('00000001', '2025-06-08', 0.2, 10)])
    r = A.flow_change(df, '2025-06-08', 7)
    assert r.value[0]['change_pct'] is None and any('under 1 cfs' in c for c in r.caveats)


def test_no_percent_of_normal_when_normal_is_a_trickle():
    """Teton at Loma showed '29,833% of normal' because normal was 0.02 cfs."""
    rows = [('00000001', f'{y}-06-01', 0.02, 10) for y in range(2015, 2025)] + [('00000001', '2025-06-01', 6, 10)]
    df, _, _ = make(rows)
    assert A.current_conditions(df).value[0]['pct_of_median'] is None
    r = A.flow_change(df, '2025-06-01', 1)
    assert r.value == [] or r.value[0]['pct_of_median'] is None


def test_flow_change_never_compares_a_day_with_itself():
    # Gap before the end date: the only reading near the 1-day target is the end date itself.
    df = make([('00000001', '2021-06-01', 100, 'nan'), ('00000001', '2021-06-05', 200, 'nan')])[0]
    r = A.flow_change(df, '2021-06-05', 1)
    assert r.value == [] and 'Test nr Town' in r.caveats[0]


def test_compare_to_normal_with_zero_normal_flow():
    rows = [('00000001', f'{y}-08-01', 0, 'nan') for y in range(2015, 2021)] + [('00000001', '2021-08-01', 5, 'nan')]
    r = A.compare_to_normal(make(rows)[0], '00000001', '2021-08-01', '2021-08-01')
    assert r.error is None and r.value['pct_of_median'] is None


def test_data_key_sees_an_edit_in_the_middle():
    a = b'x' * 20000
    assert dp.data_key(a, b's') != dp.data_key(a[:10000] + b'y' + a[10001:], b's')


@pytest.mark.parametrize('junk', [b'', b'\x1f\x8b not really gzip', b'\xff\xfe\x00\x81'])
def test_unreadable_upload_is_a_clear_error(junk):
    with pytest.raises(ValueError, match='could not be read'):
        dp.read_csv(junk)


def test_daily_file_with_no_usable_rows_is_a_clear_error():
    with pytest.raises(ValueError, match='no rows'):
        make([('00000001', 'not a date', 1, 'nan')])


def test_overlay_replaces_the_same_day_and_keeps_the_rest():
    old = pd.DataFrame({'site_no': ['1', '1', '2'], 'date': ['2026-01-01', '2026-01-02', '2026-01-02'], 'flow_cfs': ['5', '6', '7']})
    fresh = pd.DataFrame({'site_no': ['1', '1'], 'date': ['2026-01-02', '2026-01-03'], 'flow_cfs': ['60', '70']})
    out = dp.overlay(old, fresh).sort_values(['site_no', 'date'])
    assert out['flow_cfs'].tolist() == ['5', '60', '70', '7']
