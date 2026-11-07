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


def test_boat_ramps_are_trailer_ramps_only():
    import pandas as pd
    ramps = pd.read_csv(pathlib.Path(__file__).resolve().parents[1] / 'data' / 'boat_ramps.csv')
    assert len(ramps) and ramps['boat_fac'].str.contains('Ramp').all()
    assert not ramps['boat_fac'].str.contains('Hand Launch|Raft Slide').any()


def test_imagery_sits_under_names_and_shows_state_lines_at_every_zoom():
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    import theme as T
    style = {'sources': {}, 'layers': [{'id': 'water', 'type': 'fill'}, {'id': 'boundary_county', 'type': 'line'},
                                       {'id': 'boundary_state', 'type': 'line', 'minzoom': 4, 'filter': ['any']},
                                       {'id': 'water_shadow', 'type': 'fill'}, {'id': 'town', 'type': 'symbol'}]}
    out = T.with_imagery(style)
    ids = [x['id'] for x in out['layers']]
    assert 'imagery' in out['sources'] and ids.index('imagery') < ids.index('town')
    assert 'boundary_county' not in ids and 'water_shadow' not in ids
    state = next(x for x in out['layers'] if x['id'] == 'boundary_state')
    assert 'minzoom' not in state and state['filter'] == ['==', ['get', 'kind_detail'], 4]
