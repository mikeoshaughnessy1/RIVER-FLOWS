# Notes for Claude

- Show the commit and wait. Push only when Mike says "push".
- Layout in `streamlit_app.py`, math in `analytics.py`, looks in `theme.py`. Don't mix them.
- Every analytics function returns the ToolResult contract. Unknown gauges or dates return an error,
  never a guess.
- New bug = new regression test in `tests/`.
- No eval/exec, no pandas agents, no model-written code. Gemini only calls registered tools.
- USGS: use api.waterdata.usgs.gov only (legacy waterservices retires by Feb 2027).
  Keys live in Streamlit secrets, never in the repo.
- Writing in the app and docs: plain words, short sentences, no em dashes.
