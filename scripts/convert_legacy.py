"""One-time conversion of the original download (old waterservices dv format, Nov 5 2026)
into the app's columns. Kept so the snapshot's history is reproducible.
Legacy qualifiers look like "A", "P e", "P Ice": first token is approval, the rest are flags."""
import sys, pathlib
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import config

LEGACY_FLAGS = {'e': 'Estimated', 'Ice': 'Ice', 'Eqp': 'Equipment', 'Ssn': 'Seasonal',
                'Fld': 'Flood', 'Bkw': 'Backwater'}


def split(q):
    if not isinstance(q, str) or not q.strip():
        return None, ''
    parts = q.split()
    status = {'A': 'Approved', 'P': 'Provisional'}.get(parts[0])
    return status, ' '.join(LEGACY_FLAGS.get(p, p) for p in parts[1:] if not p.startswith('['))


if __name__ == '__main__':
    raw = pd.read_csv(sys.argv[1], dtype={'site_no': str}, parse_dates=['date'])
    fs = raw['flow_cfs_qual'].map(split)
    raw['flow_status'] = fs.str[0]
    raw['flow_flags'] = fs.str[1]
    raw['temp_status'] = raw['temp_mean_c_qual'].map(lambda q: split(q)[0])
    raw[config.DAILY_COLUMNS].to_csv(sys.argv[2], index=False)
    print(len(raw), 'rows ->', sys.argv[2])
