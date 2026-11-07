# Rockies build-out template

Goal: a free public river report for anglers in Montana, Idaho, Colorado and Wyoming. Someone who doesn't fish can read it. A guide can use it to plan a weekend.

## Rules for every state
- Flows only. Boat ramps stay in Montana. No other state gets ramps for now.
- Start from the key rivers an angler would name, not from every gauge.
- Fishable water stays. Low flow alone never cuts a gauge: Soda Butte and Silver Creek are small and famous. Cut only water that is clearly not fished or floated, and keep it when unsure.
- New gauges: skip any gauge that has ever dropped below 20 cfs, unless it's on a key river or known fishing water.
- Show three flow states only: below normal, near normal, above normal. Add rising, steady or dropping.
- Flow never means "good fishing". The app shows the water. The reader makes the call.
- Plain words. Technical detail stays out of the main pages.

## Fishing knowledge and voice
- Fishing facts follow the Fly Fishers International intro guide: 59 to 64°F is best for trout, oxygen drops in the upper 60s, over 70°F they don't feed, under 45°F they hold deep and slow. Stained water pushes fish toward the bank. Freestone, tailwater and spring fed are the three river types.
- Voice follows Lefty Kreh interviews and tributes: plain talk, a reason first, one dry jab at most. Trust the reader. Don't copy his lines.
- Color on the map only means a river moved or is well off normal. Steady water stays pale.
- The hatch chart is one Rocky Mountain chart for now, in `data/hatches.csv`.

## Keeping the site light
- Target about 40 gauges per state.
- The app loads one state at a time, so adding a state doesn't add memory for each visitor.
- Ship a small "normal for this date" table per gauge, not 25 years of daily rows, for new states.
- Visitors never trigger a USGS or snow data call. One scheduled job a day fetches everything, in batches.
- A failed download keeps the last good file.
- Add one state, check memory and load time on the live app, then add the next.

## Add a state
1. Fill in `data/states/<st>/rivers.csv` (columns below), key rivers first.
2. Look up each gauge's USGS site number. Confirm it's active and has flow data.
3. Apply the 20 cfs rule to anything that isn't a key river.
4. Run the history pull once and build the normals table.
5. Add the state to the daily job.
6. Check the state's seasons in `data/seasons.csv`.
7. Test, deploy, and recheck load time.

### rivers.csv
| priority | river | gauge_label | site_no | area | lat | lon |
|---|---|---|---|---|---|---|
| 1 | Madison | Madison near Ennis | fill in | Southwest | fill in | fill in |

### seasons.csv
Dates vary by river and year. Mike reviews every row. Rows here are placeholders until then.

| state | area | season | start | end | what_to_expect |
|---|---|---|---|---|---|
| MT | all | Winter midges | fill in | fill in | fill in |
| MT | all | Runoff | fill in | fill in | fill in |
| MT | all | Hoppers | fill in | fill in | fill in |
| MT | all | Fall spawn and streamers | fill in | fill in | fill in |

## Key rivers
- Montana: Missouri, Madison, Yellowstone, Gallatin, Jefferson. Add more.
- Colorado: Colorado, Eagle, Roaring Fork, Big Thompson. Add more.
- Idaho: Henry's Fork, South Fork Snake, Silver Creek, Big Wood, Salmon, Clearwater, St. Joe.
- Wyoming: first guess is North Platte, Snake, Green, Bighorn, Wind, Shoshone, Salt, Hoback.

## Build order
1. Montana cleanup: new name and headers, key rivers instead of the 10 lowest and 10 highest list, 5 years of daily data plus a normals table. Yellowstone Park stays.
2. Graphics, visualizations and style. This comes before any new feature.
3. Seasons and water temperature flags.
4. One-state-at-a-time loading with a state picker, then Colorado, Idaho and Wyoming.
5. Snowpack tab: one map per state, colored by basin percent of normal.

## Future idea: Blowout watch
Not in this build. Warn when rivers go to chocolate milk, then show which dam release rivers are steady. Example: an inch of July rain in Lamar Valley blows out Paradise Valley for 3 or more days.
- USGS `latest-continuous` gives live flow. Open-Meteo gives past and forecast rain with no key, for non-commercial use.
- USGS lists no turbidity at Corwin Springs or Livingston, so muddy water is inferred and worded "likely".
- Backtest Lamar and Soda Butte against Corwin and Livingston first to set thresholds.
- The Friday night test: an angler opens the app and sees that rain on the Colorado around State Bridge will blow out Catamount down to I-70, without pulling up every gauge.

## Open checks
- Confirm the NRCS snow data source and basin outlines before building the snowpack tab.
- Gemini's free limit resets daily, so the Ask page stays. It is low priority.
