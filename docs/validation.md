# Validation

## 1. Two USGS services agree
The history snapshot came from the legacy NWIS daily-values service. The app's refresh uses the new
Water Data API. For Aug 1 to Nov 4, 2026, all 11 gauges: **1,054 gauge-days, 0 mismatches** in flow,
mean temp, max temp and approval status.

## 2. Independent check (plain pandas, no app code)
`python scripts/independent_check.py`

| Check | Independent script | App |
|---|---|---|
| Rows / gauges | 82,876 / 11 | 82,876 / 11 (Data page) |
| Total of all daily flows | 121,623,514 cfs-days | same (Data page check sum) |
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
| Check sum up exactly 1,000: 121,624,514 | 121,624,514 ✔ |
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
