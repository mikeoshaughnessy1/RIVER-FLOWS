"""Pinned numbers from the Nov 5 2026 snapshot, checked by hand against waterdata.usgs.gov."""
import pandas as pd
import analytics as A
import config


def test_snapshot_shape(real):
    df, notes = real
    assert df['date'].min() >= pd.Timestamp(config.START_DATE) and df['site_no'].nunique() == 196
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
    assert n.loc['06-13', 'years'] > 20        # far more than the 5 years of daily rows kept


def test_runoff_trend_survives_the_trim(real):
    df, _ = real
    r = A.runoff_timing_trend(df, '06192500')
    assert not r.error and r.value['years'] > 20
