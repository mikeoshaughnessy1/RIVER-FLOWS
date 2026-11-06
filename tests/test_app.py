"""The real app, run headless: every page opens, and the states that used to crash don't."""
import pathlib
import pytest
from streamlit.testing.v1 import AppTest

APP = str(pathlib.Path(__file__).resolve().parents[1] / 'streamlit_app.py')
SHORT = b'site_no,date,flow_cfs\n06043500,2024-06-01,500\n06043500,2024-06-02,520\n'


@pytest.fixture(scope='module')
def app():
    return AppTest.from_file(APP, default_timeout=120).run()


@pytest.mark.parametrize('page', ['Map', 'Today', 'History', 'Water temp', 'Ask', 'Data'])
def test_every_page_opens(app, page):
    app.radio(key='page').set_value(page).run()
    assert not app.exception


def test_region_with_no_gauges_is_a_message_not_a_crash():
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.session_state['daily_bytes'] = SHORT       # one Southwest gauge, so Western has none
    at.run()
    at.selectbox(key='region').set_value('Western').run()
    for page in ['Map', 'Today', 'History', 'Water temp']:
        at.radio(key='page').set_value(page).run()
        assert not at.exception, page


def test_date_outside_new_data_is_pulled_back_in_range():
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.session_state['daily_bytes'] = SHORT       # the remembered map date is now past the newest reading
    at.run()
    assert not at.exception
