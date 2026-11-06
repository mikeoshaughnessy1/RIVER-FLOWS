"""River line building: every stretch has one owner, and smoothing keeps reaches connected."""
import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location(
    'fetch_reaches', pathlib.Path(__file__).resolve().parents[1] / 'scripts' / 'fetch_reaches.py')
fr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fr)


def reach(site, below, *ids):
    return {'site_no': site, 'below': below, 'segments': {i: [] for i in ids}}


def test_each_segment_goes_to_the_nearest_gauge_below():
    area = {'small': 10, 'big': 100}
    out = fr.claim([reach('big', False, 1, 2, 3), reach('small', False, 1, 2), reach('small', True, 3, 4),
                    reach('big', True, 4, 5)], area)
    owned = {(r['site_no'], r['below']): set(r['segments']) for r in out}
    assert owned == {('small', False): {1, 2}, ('big', False): {3}, ('big', True): {4, 5}}


def test_chaikin_keeps_end_points_and_rounds_corners():
    line = [(0, 0), (1, 0), (1, 1)]
    out = fr.chaikin(line, 2)
    assert out[0] == line[0] and out[-1] == line[-1] and len(out) > len(line) and (1, 0) not in out
