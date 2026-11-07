# Notes for Claude

- Show the commit and wait. Push only when Mike says "push".
- Layout in `streamlit_app.py`, math in `analytics.py`, looks in `theme.py`. Don't mix them.
- Every analytics function returns the ToolResult contract. Unknown gauges or dates return an error,
  never a guess.
- New bug = new regression test in `tests/`.
- No eval/exec, no pandas agents, no model-written code. Gemini only calls registered tools.
- USGS: use api.waterdata.usgs.gov for anything the app or scripts run (legacy waterservices
  retires by Feb 2027). The history snapshot was pulled once from legacy in Nov 2026.
  Keys live in Streamlit secrets, never in the repo.
- Large table: never filter `df[df.site_no == x]` in a loop; use `analytics._gauge(df, x)`.
- Writing in the app and docs: plain words, short sentences, no em dashes. Angler voice: dry,
  specific and matter-of-fact, one understated aside at most, no hype or exclamation marks.
