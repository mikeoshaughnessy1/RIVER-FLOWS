"""Pinned numbers from the Nov 5 2026 snapshot, checked by hand against waterdata.usgs.gov."""
import analytics as A


def test_snapshot_shape(real):
    df, notes = real
    assert len(df) == 190224 and df['site_no'].nunique() == 24
    assert not df.duplicated(['site_no', 'date']).any()


def test_known_values(real):
    df, _ = real
    # Gallatin nr Gateway, Nov 4 2026 daily mean (provisional)
    g = df[(df['site_no'] == '06043500') & (df['date'] == '2026-11-04')]
    assert g['flow_cfs'].iloc[0] == 376
    # Yellowstone nr Livingston, 2022 flood
    pk = A.annual_peaks(df, '06192500', [2022]).value[0]
    assert pk['peak_cfs'] == 43000 and pk['peak_date'] == '2022-06-13'
