"""Every gauge, parameter code, file name and column name lives here. Nothing else in the
code names a USGS code or a source column."""

# Every gauge lives in data/sites.csv (site_no, site_name, river, label, lat, lon, region).
# SITES maps site number -> (river, short label); REGION maps site number -> region.
import csv as _csv
import pathlib as _pl
_SITES_CSV = _pl.Path(__file__).parent / 'data' / 'sites.csv'
with open(_SITES_CSV, newline='') as _f:
    _rows = list(_csv.DictReader(_f))
SITES = {r['site_no']: (r['river'], r['label']) for r in _rows}
REGION = {r['site_no']: r['region'] for r in _rows}
REGIONS = ['Southwest', 'Upper Yellowstone', 'Yellowstone Park', 'Western', 'Central', 'Eastern']
# Map view per region: (center lat, center lon, zoom)
REGION_VIEW = {
    'All Montana': (46.6, -109.9, 5.65), 'Southwest': (45.4, -111.8, 6.7),
    'Upper Yellowstone': (45.4, -109.6, 6.6), 'Yellowstone Park': (44.65, -110.6, 7.8),
    'Western': (47.3, -113.6, 6.2), 'Central': (47.3, -110.6, 6.0), 'Eastern': (46.9, -106.6, 5.8),
}

START_DATE = '2000-10-01'   # start of water year 2001

# (USGS parameter code, statistic code) -> our column name
PARAMS = {
    ('00060', '00003'): 'flow_cfs',          # discharge, daily mean
    ('00010', '00003'): 'temp_mean_c',       # water temperature, daily mean
    ('00010', '00001'): 'temp_max_c',        # water temperature, daily max
}
VALUE_COLS = list(PARAMS.values())

# Uploaded / snapshot files are matched by name
FILES = {
    'daily': ('daily_values', 'daily'),     # .csv or .csv.gz     # any csv whose name contains one of these
    'sites': ('sites',),
}
DAILY_REQUIRED = ['site_no', 'date', 'flow_cfs']
SITE_REQUIRED = ['site_no', 'site_name']

# Gauges on hot springs or geyser runoff. Their water temps are real but are not river water,
# so they stay out of "warmest water" and the 73 F view.
THERMAL = {'06190540': 'Boiling River (hot spring)', '06036940': 'Tantalus Creek (geyser runoff)'}

# Fishing-relevant thresholds (Montana FWP drought/"hoot owl" policy watches 73 F daily max
# for three days in a row; FWP makes the actual call, this is only a flag).
HOOT_OWL_F = 73.0
HOOT_OWL_DAYS = 3

# Columns of data/daily_values.csv (and of anything the USGS client returns)
DAILY_COLUMNS = ['site_no', 'date', 'flow_cfs', 'temp_mean_c', 'temp_max_c',
                 'flow_status', 'flow_flags', 'temp_status']

# How far back a refresh pulls at least (recent values get revised). It goes further back when the
# snapshot is older than this: see data_prep.refresh_start.
REFRESH_DAYS = 120

# The rivers shown first on Today and the map table, in display order
KEY_RIVERS = ['Yellowstone', 'Madison', 'Missouri', 'Gallatin', 'Jefferson', 'Bighorn', 'Big Hole',
              'Beaverhead', 'Bitterroot', 'Blackfoot', 'Clark Fork', 'Kootenai']

# When someone names only a river, use this gauge (and say so in the answer's scope)
DEFAULT_GAUGE = {
    'gallatin': '06043500', 'madison': '06040000', 'yellowstone': '06192500',
    'jefferson': '06036650', 'east gallatin': '06048650', 'hyalite': '06050000',
    'shields': '06195600', 'big hole': '06025500', 'beaverhead': '06018500', 'ruby': '06023000',
    'boulder': '06033000', 'missouri': '06054500', 'clark fork': '12324200', 'red rock': '06012500',
}
# Local names people actually use -> gauge. Longer phrases are matched first.
GAUGE_ALIASES = {
    'big sky': '06043120', 'deer creek': '06043120', 'canyon': '06043120',
    'gateway': '06043500', 'gallatin gateway': '06043500',
    'logan': '06052500', 'lower gallatin': '06052500',
    'east gallatin': '06048650', 'e gallatin': '06048650', 'hyalite': '06050000',
    'cameron': '06040000', 'upper madison': '06040000', '$3 bridge': '06040000',
    'ennis lake': '06041000', 'lower madison': '06041000', 'bear trap': '06041000',
    'beartrap': '06041000', 'mcallister': '06041000',
    'three forks': '06036650', 'jefferson': '06036650',
    'corwin': '06191500', 'gardiner': '06191500', 'yankee jim': '06191500',
    'livingston': '06192500', 'paradise valley': '06192500', 'shields': '06195600',
    'wise river': '06025500', 'melrose': '06025500', 'glen': '06026210', 'barretts': '06016000',
    'dillon': '06016000', 'alder': '06019500', 'west yellowstone': '06037500', 'hebgen': '06038500',
    'toston': '06054500', 'deer lodge': '12324200', 'lima': '06012500',
}
QUESTION_LIMIT = 25     # per browser session
