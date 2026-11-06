import sys, pathlib
import pandas as pd
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import data_prep as dp


def make(rows, sites=None):
    """rows: (site_no, date, flow, temp_max_c). Builds a tiny hand-checkable dataset."""
    d = pd.DataFrame(rows, columns=['site_no', 'date', 'flow_cfs', 'temp_max_c']).astype(str)
    d['temp_mean_c'] = d['temp_max_c']
    d['flow_status'], d['flow_flags'], d['temp_status'] = 'Approved', '', ''
    s = pd.DataFrame(sites or [('00000001', 'Test River near Town', 'Test', 'Test nr Town'),
                               ('00000002', 'Other River', 'Other R', 'Other R')],
                     columns=['site_no', 'site_name', 'river', 'label']).astype(str)
    return dp.build(d, s)


@pytest.fixture
def tiny():
    rows = []
    # Same 3 days (Jun 1-3) in 2019, 2020, 2021; 2021 doubled. Site 1 only.
    for y, f in [(2019, 100), (2020, 200), (2021, 400)]:
        for day, extra in [(1, 0), (2, 10), (3, 20)]:
            rows.append(('00000001', f'{y}-06-0{day}', f + extra, 20.0))
    rows.append(('00000002', '2021-06-01', 50, 'nan'))
    return make(rows)[0]


@pytest.fixture(scope='session')
def real():
    root = pathlib.Path(__file__).resolve().parents[1] / 'data'
    df, _, notes = dp.build(pd.read_csv(root / 'daily_values.csv', dtype=str),
                            pd.read_csv(root / 'sites.csv', dtype=str))
    return df, notes
