"""Every gauge, parameter code, file name and column name lives here. Nothing else in the
code names a USGS code or a source column."""

# USGS site number -> (river, short label used in the app). Grouped by river, upstream first.
SITES = {
    '06043120': ('Gallatin', 'Gallatin abv Deer Cr (Big Sky)'),
    '06043500': ('Gallatin', 'Gallatin nr Gallatin Gateway'),
    '06052500': ('Gallatin', 'Gallatin at Logan'),
    '06050000': ('Hyalite Creek', 'Hyalite Cr at Hyalite RS'),
    '06048650': ('East Gallatin', 'E Gallatin abv Water Reclamation'),
    '06040000': ('Madison', 'Madison nr Cameron'),
    '06041000': ('Madison', 'Madison bl Ennis Lake'),
    '06036650': ('Jefferson', 'Jefferson nr Three Forks'),
    '06191500': ('Yellowstone', 'Yellowstone at Corwin Springs'),
    '06192500': ('Yellowstone', 'Yellowstone nr Livingston'),
    '06195600': ('Shields', 'Shields nr Livingston'),
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
    'daily': ('daily_values', 'daily'),     # any csv whose name contains one of these
    'sites': ('sites',),
}
DAILY_REQUIRED = ['site_no', 'date', 'flow_cfs']
SITE_REQUIRED = ['site_no', 'site_name']

# Fishing-relevant thresholds (Montana FWP drought/"hoot owl" policy watches 73 F daily max
# for three days in a row; FWP makes the actual call, this is only a flag).
HOOT_OWL_F = 73.0
HOOT_OWL_DAYS = 3

# Columns of data/daily_values.csv (and of anything the USGS client returns)
DAILY_COLUMNS = ['site_no', 'date', 'flow_cfs', 'temp_mean_c', 'temp_max_c',
                 'flow_status', 'flow_flags', 'temp_status']

# How far back the in-app "Refresh from USGS" pulls (recent values get revised while provisional)
REFRESH_DAYS = 120

# When someone names only a river, use this gauge (and say so in the answer's scope)
DEFAULT_GAUGE = {
    'gallatin': '06043500', 'madison': '06040000', 'yellowstone': '06192500',
    'jefferson': '06036650', 'east gallatin': '06048650', 'hyalite': '06050000',
    'shields': '06195600',
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
}
QUESTION_LIMIT = 25     # per browser session
