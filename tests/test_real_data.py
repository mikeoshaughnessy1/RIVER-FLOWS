"""Pinned numbers from the Nov 5 2026 snapshot, checked by hand against waterdata.usgs.gov."""
import pandas as pd
import analytics as A
import config


def test_snapshot_shape(real):
    df, notes = real
    assert df['date'].min() >= pd.Timestamp(config.START_DATE) and df['site_no'].nunique() == 184
    assert not df.duplicated(['site_no', 'date']).any()


def test_known_values(real):
    df, _ = real
    # Gallatin nr Gateway, Nov 4 2026 daily mean (provisional)
    g = df[(df['site_no'] == '06043500') & (df['date'] == '2026-11-04')]
    assert g['flow_cfs'].iloc[0] == 376
    # Yellowstone nr Livingston, 2022 flood
    pk = A.annual_peaks(df, '06192500', [2022]).value[0]
    assert pk['peak_cfs'] == 43000 and pk['peak_date'] == '2022-06-13'


def test_normal_still_uses_every_year(real):
    df, _ = real
    n = A.daily_normals(A._gauge(df, '06192500'), 2026)
    assert n.loc['06-13', 'years'] > 20        # far more than the 10 years of daily rows kept


def test_uploaded_data_gets_its_own_normal(real):
    df, _ = real
    g = A._gauge(df, '06192500').assign(uploaded=True, flow_cfs=lambda d: d['flow_cfs'] * 10)
    assert A.daily_normals(g, 2026).loc['06-13', 'median'] > 5 * A.daily_normals(A._gauge(df, '06192500'), 2026).loc['06-13', 'median']


def test_peaks_reach_past_the_kept_years(real):
    df, _ = real
    peaks = {p['water_year']: p for p in A.annual_peaks(df, '06192500').value}
    assert min(peaks) <= 2002 and len(peaks) > 20
    assert peaks[2022]['peak_cfs'] == 43000
    assert peaks[2016]['days_with_data'] >= A.FULL_YEAR_DAYS      # first kept year is whole, from the saved table
    assert A.annual_peaks(df, '06192500', [2011]).value[0]['water_year'] == 2011


def test_runoff_trend_works_by_number_and_by_name(real):
    df, _ = real
    label = A._gauge(df, '06192500')['label'].iloc[0]
    for site in ('06192500', label):
        r = A.runoff_timing_trend(df, site)
        assert not r.error and r.value['years'] > 20


def test_no_stub_year_on_the_water_temp_chart(real):
    df, _ = real
    rows = {r['year']: r for r in A.hot_water_by_year(df, '06052500').value}
    assert rows[2021]['days_at_or_above'] == 38
