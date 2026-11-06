# Bozeman River Report

A Streamlit app for the rivers around Bozeman, built on USGS gauge data. Same build as our
E-Presso BI app (tool-calling assistant, upload and recalculate, validation), pointed at water
instead of coffee.

**What it shows**

1. **Today**: every gauge's latest daily flow vs the median for that date, 7-day change, water temp,
   and this water year's hydrograph against the 10th to 90th percentile band.
2. **History**: when each river peaked every year, typical flow by month, and any date window ranked
   against every earlier year.
3. **Water temp**: days at or above 73°F (the number Montana FWP watches for hoot-owl
   restrictions) and 3+ day runs.
4. **Ask**: plain-English questions. Gemini picks a tool and every number comes from that tool.
   No key? A keyword router answers instead.
5. **Data**: refresh from USGS, upload changed files, load notes, data quality by gauge.

## Gauges (11)

| River | Gauge | USGS site |
|---|---|---|
| Gallatin | above Deer Creek (Big Sky) | 06043120 |
| Gallatin | near Gallatin Gateway | 06043500 |
| Gallatin | at Logan | 06052500 |
| Hyalite Creek | at Hyalite Ranger Station | 06050000 |
| East Gallatin | above Water Reclamation Facility | 06048650 |
| Madison | near Cameron | 06040000 |
| Madison | below Ennis Lake (Bear Trap) | 06041000 |
| Jefferson | near Three Forks | 06036650 |
| Yellowstone | at Corwin Springs | 06191500 |
| Yellowstone | near Livingston | 06192500 |
| Shields | near Livingston | 06195600 |

Daily mean discharge (cfs) plus daily mean and max water temperature, water year 2001
(Oct 1, 2000) through Nov 4, 2026. 82,876 gauge-days.

## Data

- `data/daily_values.csv`: one row per gauge per day. Columns: `site_no, date, flow_cfs,
  temp_mean_c, temp_max_c, flow_status (Approved/Provisional), flow_flags (Estimated, Ice...),
  temp_status`.
- `data/sites.csv`: gauge names, river, short label, lat/lon.
- The app loads these on open. **Refresh from USGS** pulls the last 120 days from the
  [USGS Water Data API](https://api.waterdata.usgs.gov/) and lays it over the snapshot.
- `scripts/fetch_usgs.py` rebuilds the whole file from the API.

The old waterservices.usgs.gov service is being shut down (Nov 2026 to Feb 2027), so the app
only uses the new API. Without a free USGS API key you get only a few requests an hour.

## Files

| File | Job |
|---|---|
| `config.py` | Gauges, USGS codes, column names, thresholds, local nicknames. Nothing else names a source column. |
| `usgs.py` | USGS API client. Returns tidy tables. |
| `data_prep.py` | Cleans both tables, joins them with a row-count check, writes load notes. |
| `analytics.py` | All the math. Pure functions returning `{tool, value, definition, scope, rows_used, caveats, error}`. |
| `agent.py` | Tool registry, rules router, Gemini router, answer format. |
| `theme.py` | Colors, CSS, chart template. Looks only. |
| `streamlit_app.py` | Layout only. |
| `tests/` | Hand-checkable unit tests plus regression tests for bugs found. |
| `docs/validation.md` | How we checked the numbers. |

## Run it

```
pip install -r requirements.txt
streamlit run streamlit_app.py
python -m pytest -q
python scripts/independent_check.py
```

## Deploy

share.streamlit.io → New app → this repo, branch `main`, file `streamlit_app.py`.
Then Manage app → Settings → Secrets, paste from `.streamlit/secrets.toml.example`
(Gemini key from AI Studio, free USGS key from api.waterdata.usgs.gov/signup).

## Limits

Gauge data shows what happened, not why, and it doesn't forecast. Recent values are provisional
and USGS revises them. Several gauges have no temperature sensor or only seasonal ones. The
Madison is dam-controlled. This is not a safety tool and not a source for FWP rules.
