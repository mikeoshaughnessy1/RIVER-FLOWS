"""The real app, run headless: every page opens, and the states that used to crash don't."""
import pathlib
import pytest
from streamlit.testing.v1 import AppTest

APP = str(pathlib.Path(__file__).resolve().parents[1] / 'streamlit_app.py')
SHORT = b'site_no,date,flow_cfs\n06043500,2024-06-01,500\n06043500,2024-06-02,520\n'


def upload(at, data):
    at.session_state['daily_bytes'], at.session_state['recent_bytes'] = data, b''
    at.session_state['daily_src'] = 'Uploaded test.csv'


@pytest.fixture(scope='module')
def app():
    return AppTest.from_file(APP, default_timeout=120).run()


@pytest.mark.parametrize('page', ['Map', 'Today', 'History', 'Water temp', 'Ask', 'Data'])
def test_every_page_opens(app, page):
    app.radio(key='page').set_value(page).run()
    assert not app.exception


def test_region_with_no_gauges_is_a_message_not_a_crash():
    at = AppTest.from_file(APP, default_timeout=120).run()
    upload(at, SHORT)       # one Southwest gauge, so Western has none
    at.run()
    at.selectbox(key='region').set_value('Western').run()
    for page in ['Map', 'Today', 'History', 'Water temp']:
        at.radio(key='page').set_value(page).run()
        assert not at.exception, page


def test_date_outside_new_data_is_pulled_back_in_range():
    at = AppTest.from_file(APP, default_timeout=120).run()
    upload(at, SHORT)       # the remembered map date is now past the newest reading
    at.run()
    assert not at.exception


def test_data_note_link_opens_the_issues_section():
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.button(key='to_data').click().run()
    assert at.radio(key='page').value == 'Data' and not at.exception
    text = ' '.join(m.value for m in at.markdown)
    assert 'Data issues found' in text and 'negative flow' in text and 'no flow reading' in text


def test_tab_open_across_a_deploy_gets_the_recent_file():
    at = AppTest.from_file(APP, default_timeout=120).run()
    del at.session_state['recent_bytes']
    at.run()
    assert not at.exception and at.session_state['recent_bytes']


def test_old_tab_moves_to_the_current_recent_file():
    at = AppTest.from_file(APP, default_timeout=120).run()
    current = at.session_state['recent_bytes']
    at.session_state['recent_bytes'] = b'yesterday'
    at.run()
    assert not at.exception and at.session_state['recent_bytes'] == current


def test_uploaded_data_is_not_overlaid_with_the_recent_file():
    at = AppTest.from_file(APP, default_timeout=120).run()
    upload(at, SHORT)
    at.run()
    assert not at.exception and at.session_state['recent_bytes'] == b''


def test_data_page_does_not_say_provisional(app):
    app.radio(key='page').set_value('Data').run()
    assert 'provisional' not in ' '.join(x.value for x in [*app.markdown, *app.caption]).lower()
