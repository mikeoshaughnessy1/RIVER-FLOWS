"""Load and clean the two tables and join them into one fact table: one row per gauge per day.

Every problem found is written to `notes` (shown on the Data page) instead of crashing.
"""
from __future__ import annotations
import hashlib
import io
import zlib
import pandas as pd
import config


def note(notes: list, level: str, msg: str):
    notes.append({'level': level, 'message': msg})


def read_csv(file_bytes: bytes) -> pd.DataFrame:
    gz = file_bytes[:2] == b'\x1f\x8b'          # gzip magic number
    try:
        return pd.read_csv(io.BytesIO(file_bytes), dtype=str, keep_default_na=True,
                           compression='gzip' if gz else None)
    except (OSError, EOFError, zlib.error, ValueError) as e:     # ValueError covers empty and undecodable files
        raise ValueError(f'That file could not be read as a CSV ({type(e).__name__}).') from e


def data_key(daily_bytes: bytes, sites_bytes: bytes) -> str:
    """Cache key for the loaded data. Hashes every byte, so an edit anywhere shows new numbers."""
    return hashlib.md5(daily_bytes + b'|' + sites_bytes).hexdigest()


def clean_sites(raw: pd.DataFrame, notes: list) -> pd.DataFrame:
    missing = [c for c in config.SITE_REQUIRED if c not in raw.columns]
    if missing:
        raise ValueError(f'Sites file is missing required column(s): {missing}')
    s = raw.copy()
    s['site_no'] = s['site_no'].astype(str).str.strip().str.zfill(8)
    for c in ('river', 'label'):
        if c not in s.columns:
            s[c] = None
    s['label'] = s['label'].fillna(s['site_name'])
    s['river'] = s['river'].fillna('Other')
    for c in ('lat', 'lon'):
        s[c] = pd.to_numeric(s.get(c), errors='coerce')
    dups = s.duplicated('site_no', keep='first')
    if dups.any():
        note(notes, 'warn', f'Sites file has {int(dups.sum())} duplicate site number(s) '
                            f'({", ".join(s.loc[dups, "site_no"])}); kept the first row of each.')
        s = s[~dups]
    if 'region' not in s.columns:
        s['region'] = s['site_no'].map(config.REGION).fillna('Other')
    s['region'] = s['region'].fillna('Other')
    return s[['site_no', 'site_name', 'river', 'label', 'lat', 'lon', 'region']].reset_index(drop=True)


def clean_daily(raw: pd.DataFrame, notes: list) -> pd.DataFrame:
    missing = [c for c in config.DAILY_REQUIRED if c not in raw.columns]
    if missing:
        raise ValueError(f'Daily values file is missing required column(s): {missing}. '
                         f'Expected columns like {config.DAILY_COLUMNS}.')
    d = raw.copy()
    for c in config.DAILY_COLUMNS:
        if c not in d.columns:
            d[c] = None
    # Excel drops the leading zero from "06043500"; put it back
    d['site_no'] = d['site_no'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True).str.zfill(8)
    dates = pd.to_datetime(d['date'], errors='coerce', format='mixed')
    bad = dates.isna()
    if bad.any():
        note(notes, 'warn', f'{int(bad.sum())} row(s) had a blank or unreadable date and were dropped.')
    d['date'] = dates.dt.normalize()
    d = d[~bad]
    for c in config.VALUE_COLS:
        num = pd.to_numeric(d[c], errors='coerce')
        junk = num.isna() & d[c].notna() & (d[c].astype(str).str.strip() != '')
        if junk.any():
            note(notes, 'warn', f'{int(junk.sum())} non-numeric value(s) in {c} were treated as missing '
                                f'(e.g. "{d.loc[junk, c].iloc[0]}").')
        d[c] = num
    neg = d['flow_cfs'] < 0
    if neg.any():
        note(notes, 'warn', f'{int(neg.sum())} negative flow value(s) were treated as missing.')
        d.loc[neg, 'flow_cfs'] = pd.NA
    dups = d.duplicated(['site_no', 'date'], keep='last')
    if dups.any():
        note(notes, 'warn', f'{int(dups.sum())} duplicate site/day row(s); kept the last one of each.')
        d = d[~dups]
    for c in ('flow_status', 'flow_flags', 'temp_status'):
        d[c] = d[c].fillna('').astype(str)
    return d[config.DAILY_COLUMNS].sort_values(['site_no', 'date']).reset_index(drop=True)


def check_merge(daily: pd.DataFrame, sites: pd.DataFrame, notes: list) -> pd.DataFrame:
    """Left-join gauges onto daily rows; record rows before/after and any unmatched gauges."""
    before = len(daily)
    out = daily.merge(sites, on='site_no', how='left', validate='many_to_one')
    if len(out) != before:  # cannot happen with a unique lookup, but prove it
        raise ValueError(f'Join changed the row count ({before} -> {len(out)}).')
    unmatched = sorted(out.loc[out['label'].isna(), 'site_no'].unique())
    if unmatched:
        note(notes, 'warn', f'Gauge(s) {", ".join(unmatched)} are not in the sites file; '
                            f'shown by site number under river "Other".')
        out['label'] = out['label'].fillna(out['site_no'])
        out['site_name'] = out['site_name'].fillna(out['site_no'])
        out['river'] = out['river'].fillna('Other')
        out['region'] = out['region'].fillna('Other')
    note(notes, 'ok', f'Joined {before:,} daily rows to {sites["site_no"].nunique()} gauges; '
                      f'row count unchanged.')
    return out


def build(daily_raw: pd.DataFrame, sites_raw: pd.DataFrame):
    notes: list = []
    sites = clean_sites(sites_raw, notes)
    daily = clean_daily(daily_raw, notes)
    if daily.empty:
        raise ValueError('The daily values file has no rows with a readable date.')
    df = check_merge(daily, sites, notes)
    df['water_year'] = df['date'].dt.year + (df['date'].dt.month >= 10).astype(int)
    df['year'] = df['date'].dt.year
    df['month'] = df['date'].dt.month
    df['md'] = df['date'].dt.strftime('%m-%d')
    df['temp_mean_f'] = df['temp_mean_c'] * 9 / 5 + 32
    df['temp_max_f'] = df['temp_max_c'] * 9 / 5 + 32
    # 1.5M rows: store repeated text as categories and drop columns the math never uses
    df = df.drop(columns=['site_name', 'lat', 'lon'])
    for c in ('site_no', 'label', 'river', 'region', 'md', 'flow_status', 'flow_flags', 'temp_status'):
        df[c] = df[c].astype('category')
    for c in ('water_year', 'year', 'month'):
        df[c] = df[c].astype('int16')
    return df, sites, notes


def merge_refresh(old_raw: pd.DataFrame, fresh: pd.DataFrame) -> pd.DataFrame:
    """Lay freshly downloaded rows over the snapshot (recent provisional values get revised)."""
    old = old_raw.copy()
    old['date'] = pd.to_datetime(old['date'], errors='coerce')
    old['site_no'] = old['site_no'].astype(str).str.zfill(8)
    fresh = fresh.copy()
    fresh['date'] = pd.to_datetime(fresh['date'])
    key = ['site_no', 'date']
    keep = old.merge(fresh[key], on=key, how='left', indicator=True)['_merge'] == 'left_only'
    out = pd.concat([old[keep.values], fresh], ignore_index=True)
    out['date'] = out['date'].dt.strftime('%Y-%m-%d')
    return out.astype({c: str for c in ('flow_status', 'flow_flags', 'temp_status')})
