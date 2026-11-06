# Validation

## 1. Two USGS services agree
The history snapshot came from the legacy NWIS daily-values service. The app's refresh uses the new
Water Data API. For Aug 1 to Nov 4, 2026, the original 11 gauges: **1,054 gauge-days, 0 mismatches** in flow,
mean temp, max temp and approval status.

## 2. Independent check (plain pandas, no app code)
`python scripts/independent_check.py`

| Check | Independent script | App |
|---|---|---|
| Rows / gauges | 1,561,205 / 199 | 1,561,205 / 199 (Data page) |
| Total of all daily flows, negatives removed | 2,549,771,955 cfs-days | same (Data page check sum) |
| Gallatin nr Gateway, Nov 4 2026 | 376 cfs, median 379, 99% | 376, 379, 99% (Today) |
| Gallatin at Logan, 2021 days ≥ 73°F | 38 | 38 (Water temp; Ask) |
| Jefferson, 2025 days < 500 cfs | 83 | 83 (Ask) |
| Yellowstone nr Livingston, WY2022 peak | 43,000 cfs on 2022-06-13 | same (History; Ask) |

To do ourselves: spot-check 3 of these on waterdata.usgs.gov and screenshot.

## 3. The +1,000 test
Changed one cell: Gallatin nr Gallatin Gateway (06043500), 2026-07-15, flow 726 → 1,726 cfs.
Diffed against the original: 1 cell changed, every date still parses.

| Prediction (written before upload) | Result after upload, no restart |
|---|---|
| Check sum up exactly 1,000: 2,549,772,955 | 2,549,772,955 ✔ |
| July 2026 mean at Gateway up 1,000 / 31 = 32.3 cfs (798 → 830) | 798 → 830 ✔ |
| July 2026 high becomes 1,726 on Jul 15 | 1,726 on 2026-07-15 ✔ |
| WY2026 peak unchanged (2,760 on May 31) | unchanged ✔ |
| Other gauges unchanged | unchanged ✔ |

To do ourselves: redo on the live app with screenshots before, after, and after Restore.

## 4. Messy files (no tracebacks)
| File | App response |
|---|---|
| "Ice" in a flow cell | treated as missing, load note |
| Blank date | row dropped, load note |
| Negative flow | treated as missing, load note |
| Duplicate gauge-day | kept the last, load note |
| Leading zeros stripped (Excel) | restored ("6043500" → "06043500") |
| Gauge not in sites file | kept, labelled by number, load note |
| Missing `flow_cfs` column | plain message + Restore button |
| Partial water year | peaks flagged as partial |
| Gauge with no temp sensor | says so and lists gauges that have temps that year |

## 5. Assistant tests
Unit tests cover routing for 5 question types plus forecast, safety and rules flags.

Bug found and fixed: "How is the Gallatin running?" went to the **East** Gallatin because
"th**e gallatin**" contains the alias "e gallatin". Aliases now match whole words only.
Regression test: `test_the_gallatin_is_not_east_gallatin`.

To do ourselves: 5 questions on the live app with Gemini on, screenshot each Method log.

## 6. Map
- `flow_change` is checked by hand in tests (100 → 150 cfs over 7 days = +50%; 150 → 75 in 1 day = -50%).
- River lines come from the USGS river network above each gauge. Big rivers are drawn first and
  smaller gauges on top, so each stretch takes the color of the nearest gauge below it. Checked by
  plotting all 24 reaches: rivers join at Three Forks and Twin Bridges with no gaps.
- Color is never the only signal: hover shows cfs and percent, and a ranked table sits under the map.
- Bug found: a gauge with only one year of data crashed the "normal" calculation. Fixed; regression
  test `test_gauge_with_one_year_has_no_normal_but_no_crash`.

## 7. Statewide (199 gauges)
- Gauges: every active Montana river gauge with 10+ years of daily flow (no ditches or canals),
  plus Yellowstone Park gauges and Big Sky. Regions come from the USGS basin code.
- The raw file has 6 negative daily flows (Belt Cr Dec 2021, Peoples Cr May 2002, -4.08 cfs-days
  total). The app treats them as missing and says so in the load notes. The independent script
  prints both totals; the "negatives removed" one matches the app exactly.
- Percent change is left blank when flow started under 1 cfs (0.3 to 0.2 cfs is not a "-33% drop").
  Regression test `test_no_percent_change_on_a_trickle`.
- Speed: map draws went from 23 s to under 3 s (rows split by gauge once instead of scanned
  per gauge) and memory from 400 MB to 100 MB (text stored as categories). Draws are cached.
- Checked by plotting the June 14, 2022 Yellowstone flood: the Yellowstone and southwest rivers
  show as rising statewide.
