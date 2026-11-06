"""The assistant. It never does math itself: every number comes from an analytics tool.

TOOLS registry -> run_tool (checks args, runs, logs) -> router.
Router: Gemini function calling when a key is set (tools only, fixed gauge list),
otherwise (or on any API error) a keyword rules router. Answers come back as
Scope / Findings / Interpretation / Next steps plus the tool log.
"""
from __future__ import annotations
import json, re
import pandas as pd
import analytics as A
import config

MONTHS = {m.lower(): i for i, m in enumerate(
    ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
     'September', 'October', 'November', 'December'], 1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})

S = {'type': 'string'}
TOOLS = {
    'current_conditions': {'fn': A.current_conditions,
        'desc': 'Latest daily flow at gauges vs the median for that calendar day, 7-day change, '
                'latest water temp. Use for "how is X running", "flows right now".',
        'params': {'sites': {'type': 'array', 'items': {'type': 'string', 'enum': '__SITES__'}}}},
    'flow_stats': {'fn': A.flow_stats,
        'desc': 'Mean/median/min/max daily flow and volume at one gauge over a date window.',
        'params': {'site': {'type': 'string', 'enum': '__SITES__'}, 'start': S, 'end': S},
        'required': ['site']},
    'compare_to_normal': {'fn': A.compare_to_normal,
        'desc': 'Mean flow over a window (<= 1 year) vs the same window in every earlier year: '
                'percent of median, rank, wettest and driest years.',
        'params': {'site': {'type': 'string', 'enum': '__SITES__'}, 'start': S, 'end': S},
        'required': ['site', 'start', 'end']},
    'annual_peaks': {'fn': A.annual_peaks,
        'desc': 'Peak daily flow and its date per water year (Oct 1-Sep 30): runoff size and timing.',
        'params': {'site': {'type': 'string', 'enum': '__SITES__'},
                   'water_years': {'type': 'array', 'items': {'type': 'integer'}}},
        'required': ['site']},
    'runoff_timing_trend': {'fn': A.runoff_timing_trend,
        'desc': 'Trend in the date of the annual peak (is runoff coming earlier?).',
        'params': {'site': {'type': 'string', 'enum': '__SITES__'}}, 'required': ['site']},
    'monthly_flow': {'fn': A.monthly_flow,
        'desc': 'Mean and median flow by calendar month at one gauge.',
        'params': {'site': {'type': 'string', 'enum': '__SITES__'},
                   'water_years': {'type': 'array', 'items': {'type': 'integer'}}},
        'required': ['site']},
    'hot_water_days': {'fn': A.hot_water_days,
        'desc': 'Days in a calendar year when daily max water temp hit a threshold (default 73 F, '
                'the hoot-owl number) and 3+ day runs.',
        'params': {'site': {'type': 'string', 'enum': '__SITES__'}, 'year': {'type': 'integer'},
                   'threshold_f': {'type': 'number'}}, 'required': ['site', 'year']},
    'hot_water_by_year': {'fn': A.hot_water_by_year,
        'desc': 'Hot-water day counts for every year with temperature data at one gauge.',
        'params': {'site': {'type': 'string', 'enum': '__SITES__'}, 'threshold_f': {'type': 'number'}},
        'required': ['site']},
    'low_flow_days': {'fn': A.low_flow_days,
        'desc': 'Days in a calendar year with flow below a cfs threshold, and the lowest day.',
        'params': {'site': {'type': 'string', 'enum': '__SITES__'}, 'year': {'type': 'integer'},
                   'threshold_cfs': {'type': 'number'}}, 'required': ['site', 'year', 'threshold_cfs']},
    'compare_gauges': {'fn': A.compare_gauges,
        'desc': 'Compare 2+ gauges over the same window (stats and percent of median).',
        'params': {'sites': {'type': 'array', 'items': {'type': 'string', 'enum': '__SITES__'}},
                   'start': S, 'end': S}, 'required': ['sites']},
    'flow_change': {'fn': A.flow_change,
        'desc': 'Percent change in flow over N days (default 7) ending on a date, at all or some gauges. '
                'Use for "what is rising/dropping", "biggest change this week", the map page.',
        'params': {'as_of': S, 'window_days': {'type': 'integer'},
                   'sites': {'type': 'array', 'items': {'type': 'string', 'enum': '__SITES__'}}}},
    'list_gauges': {'fn': A.list_gauges, 'desc': 'List the gauges and their periods of record.',
                    'params': {}},
    'data_quality_report': {'fn': A.data_quality_report, 'needs_notes': True,
        'desc': 'Missing days, provisional and estimated values, ice, temp coverage per gauge.',
        'params': {}},
}


def run_tool(name: str, args: dict, df, log: list, notes=None) -> dict:
    if name not in TOOLS:
        res = A.ToolResult(name, error=f'Unknown tool {name}.').to_dict()
    else:
        spec = TOOLS[name]
        allowed = set(spec['params'])
        extra = set(args) - allowed
        missing = [p for p in spec.get('required', []) if p not in args]
        if extra or missing:
            res = A.ToolResult(name, error=f'Bad arguments. Unexpected {sorted(extra)}, missing {missing}.').to_dict()
        else:
            try:
                kw = {'notes': notes} if spec.get('needs_notes') else {}
                res = spec['fn'](df, **kw, **args).to_dict()
            except Exception as e:  # a tool bug must never crash the page
                res = A.ToolResult(name, error=f'Tool failed: {type(e).__name__}: {e}').to_dict()
    log.append({'tool': name, 'args': args, 'result': res})
    return res


# ---------- what kind of question is this ----------

def question_flags(q: str) -> list[str]:
    q = q.lower()
    flags = []
    if re.search(r'\b(forecast|predict|will (it|the)|next (week|month|year|spring|summer)|tomorrow|going to)\b', q):
        flags.append('Forecast: this app only has past and current gauge data. It can show what is normal '
                     'for the coming weeks, but not predict them. NRCS SNOTEL snowpack and NWS river '
                     'forecasts are the right sources.')
    if re.search(r'\b(why|because|cause[ds]?|due to)\b', q):
        flags.append('Cause: gauge data shows what happened, not why. Snowpack, rain, dams and '
                     'irrigation all move these numbers.')
    if re.search(r'\b(safe|dangerous|float|wade|wading|row|boat)\b', q):
        flags.append('Safety: flow numbers are not a safety call. Check the gauge trend, local '
                     'shops, and your own skill; high or rising water is dangerous.')
    if re.search(r'\b(closed|closure|hoot.?owl|restriction|legal|regulation)\b', q):
        flags.append('Rules: Montana FWP announces closures and hoot-owl restrictions (fwp.mt.gov). '
                     'This app only shows the temperature and flow pattern they watch.')
    return flags


def find_gauges(q: str, df) -> tuple[list[str], list[str]]:
    """Gauges named in the question, plus notes on any river-only defaults used."""
    ql = q.lower()
    loaded = set(df['site_no'].unique())
    found, notes = [], []
    for sn in re.findall(r'\b0\d{7}\b', q):
        if sn in loaded and sn not in found:
            found.append(sn)
    taken = ql
    for alias in sorted(config.GAUGE_ALIASES, key=len, reverse=True):
        pat = rf'(?<![a-z]){re.escape(alias)}(?![a-z])'   # whole words: "the gallatin" is not "e gallatin"
        if re.search(pat, taken):
            sn = config.GAUGE_ALIASES[alias]
            if sn in loaded and sn not in found:
                found.append(sn)
            taken = re.sub(pat, ' ', taken)
    for river in sorted(config.DEFAULT_GAUGE, key=len, reverse=True):
        if re.search(rf'\b{river}\b', taken):
            sn = config.DEFAULT_GAUGE[river]
            if sn in loaded and sn not in found:
                found.append(sn)
                label = df.loc[df['site_no'] == sn, 'label'].iloc[0]
                notes.append(f'"{river.title()}" read as {label}. Name a spot (e.g. Logan, Big Sky) for another gauge.')
            taken = re.sub(rf'\b{river}\b', ' ', taken)
    return found, notes


def find_window(q: str, df) -> tuple[str | None, str | None]:
    ql = q.lower()
    last = df['date'].max()
    years = [int(y) for y in re.findall(r'\b(19\d\d|20\d\d)\b', q)]
    if 'this year' in ql:
        years.append(last.year)
    if 'last year' in ql:
        years.append(last.year - 1)
    month = next((MONTHS[w] for w in re.findall(r'[a-z]+', ql) if w in MONTHS and w != 'may'
                  or (w == 'may' and re.search(r'\bmay\b(?! be)', ql))), None)
    if month:
        y = years[0] if years else (last.year if month <= last.month else last.year - 1)
        s = pd.Timestamp(year=y, month=month, day=1)
        return str(s.date()), str((s + pd.offsets.MonthEnd(0)).date())
    if years:
        return f'{min(years)}-01-01', f'{max(years)}-12-31'
    m = re.search(r'last (\d+) days', ql)
    if m:
        return str((last - pd.Timedelta(days=int(m.group(1)) - 1)).date()), str(last.date())
    if 'last week' in ql or 'past week' in ql:
        return str((last - pd.Timedelta(days=6)).date()), str(last.date())
    if 'last month' in ql or 'past month' in ql or 'last 30' in ql:
        return str((last - pd.Timedelta(days=29)).date()), str(last.date())
    return None, None


def rules_route(q: str, df) -> tuple[str, dict, list[str]]:
    ql = q.lower()
    gauges, notes = find_gauges(q, df)
    start, end = find_window(q, df)
    years = [int(y) for y in re.findall(r'\b(20\d\d)\b', q)]
    year = years[0] if years else (df['date'].max().year - (1 if 'last year' in ql else 0))
    site = gauges[0] if gauges else None

    if re.search(r'\b(rising|dropping|falling|coming up|going down|drop|rise|changed?|changing)\b', ql) \
            and not re.search(r'\b(peak|runoff|earlier|trend)\b', ql):
        m = re.search(r'(\d+)[- ]day', ql)
        days = int(m.group(1)) if m else (1 if re.search(r'\b(today|yesterday|overnight)\b', ql) else
                                          30 if 'month' in ql else 7)
        args = {'window_days': days}
        if gauges:
            args['sites'] = gauges
        if start and end:
            args['as_of'] = end
        return 'flow_change', args, notes
    if re.search(r'\b(missing|quality|clean|provisional|estimated|gaps?|bad data)\b', ql):
        return 'data_quality_report', {}, notes
    if re.search(r'\b(which|what|list) (gauges|sites|rivers)\b', ql):
        return 'list_gauges', {}, notes
    if re.search(r'\b(temp|temperature|hot|warm|hoot.?owl|73)\b', ql):
        site = site or '06052500'
        if not gauges:
            notes.append('No gauge named; used Gallatin at Logan, which has a temperature sensor.')
        if re.search(r'\b(every|each|by) year\b|\byears\b|\bworst\b', ql) and not years:
            return 'hot_water_by_year', {'site': site}, notes
        return 'hot_water_days', {'site': site, 'year': year}, notes
    if len(gauges) >= 2 and re.search(r'\b(compare|vs|versus|or|and|between)\b', ql):
        s, e = (start, end) if start else (
            str((df['date'].max() - pd.Timedelta(days=29)).date()), str(df['date'].max().date()))
        return 'compare_gauges', {'sites': gauges, 'start': s, 'end': e}, notes
    site = site or config.DEFAULT_GAUGE['gallatin']
    if not gauges and not re.search(r'\b(all|every|rivers)\b', ql):
        notes.append('No gauge named; used Gallatin nr Gallatin Gateway.')
    if re.search(r'\b(peak|runoff|high water)\b', ql):
        if re.search(r'\b(earlier|later|trend|timing|shift|changing)\b', ql):
            return 'runoff_timing_trend', {'site': site}, notes
        return 'annual_peaks', ({'site': site, 'water_years': years} if years else {'site': site}), notes
    m = re.search(r'(below|under|less than)\s*([\d,]+)\s*(cfs)?', ql)
    if m:
        return 'low_flow_days', {'site': site, 'year': year,
                                 'threshold_cfs': float(m.group(2).replace(',', ''))}, notes
    if re.search(r'\b(month|monthly|by month)\b', ql) and not start:
        return 'monthly_flow', {'site': site}, notes
    if re.search(r'\b(normal|average|median|typical|compared to|usual|percent)\b', ql) and start:
        return 'compare_to_normal', {'site': site, 'start': start, 'end': end}, notes
    if start and re.search(r'\b(mean|max|highest|lowest|min|volume|stats?|flow)\b', ql):
        return 'flow_stats', {'site': site, 'start': start, 'end': end}, notes
    sites = gauges or (None if re.search(r'\b(all|every|rivers)\b', ql) else [site])
    return 'current_conditions', ({'sites': sites} if sites else {}), notes


# ---------- writing the answer (rules mode) ----------

def _f(x, nd=0):
    return '-' if x is None or (isinstance(x, float) and pd.isna(x)) else f'{x:,.{nd}f}'


def describe(res: dict) -> str:
    v, t = res['value'], res['tool']
    if res['error']:
        return res['error']
    if t == 'current_conditions':
        lines = []
        for r in v:
            pm = f", {_f(r['pct_of_median'])}% of the median for the date" if r['pct_of_median'] else ''
            tmp = f", water {_f(r['water_temp_max_f'], 1)} F max" if r['water_temp_max_f'] else ''
            ch = f", {_f(r['change_7d_pct'], 0)}% over 7 days" if r['change_7d_pct'] is not None else ''
            lines.append(f"{r['gauge']}: {_f(r['flow_cfs'])} cfs on {r['date']}{pm}{ch}{tmp}.")
        return '\n'.join(lines) or 'No current flow at those gauges.'
    if t == 'flow_stats':
        return (f"Mean {_f(v['mean_cfs'])} cfs (median {_f(v['median_cfs'])}). High {_f(v['max_cfs'])} cfs on "
                f"{v['max_date']}, low {_f(v['min_cfs'])} cfs on {v['min_date']}. About "
                f"{_f(v['volume_acre_ft'])} acre-feet went by.")
    if t == 'compare_to_normal':
        return (f"Mean {_f(v['window_mean_cfs'])} cfs vs a median of {_f(v['median_of_other_years_cfs'])} "
                f"for the same dates in {v['years_compared']} earlier years: {_f(v['pct_of_median'])}% of normal, "
                f"rank {v['rank']}. Wettest {v['wettest']['year']} ({_f(v['wettest']['mean_cfs'])} cfs), "
                f"driest {v['driest']['year']} ({_f(v['driest']['mean_cfs'])} cfs).")
    if t == 'annual_peaks':
        rows = v[-6:]
        return 'Peak daily flow by water year: ' + '; '.join(
            f"{r['water_year']}: {_f(r['peak_cfs'])} cfs on {r['peak_date']}" for r in rows) + '.'
    if t == 'runoff_timing_trend':
        d = v['days_per_decade']
        way = 'earlier' if d < 0 else 'later'
        return (f"Median peak is {v['median_peak_date']} over {v['years']} full years. The fitted line moves "
                f"{_f(abs(d), 1)} days {way} per decade, but R-squared is {_f(v['r_squared'], 2)}, so year-to-year "
                f"weather explains far more than any trend.")
    if t == 'hot_water_days':
        runs = v['runs_of_3_plus_days']
        rs = ('; '.join(f"{r['from']} to {r['to']} ({r['days']} days)" for r in runs)) or 'none'
        return (f"{v['days_at_or_above']} day(s) with max water temp at or above {v['threshold_f']:g} F. "
                f"Hottest {_f(v['hottest_f'], 1)} F on {v['hottest_date']}. Runs of 3+ days: {rs}.")
    if t == 'hot_water_by_year':
        top = sorted(v, key=lambda r: -r['days_at_or_above'])[:5]
        return 'Most hot-water days: ' + '; '.join(f"{r['year']}: {r['days_at_or_above']}" for r in top) + '.'
    if t == 'low_flow_days':
        first = f", first on {v['first_day_below']}" if v['first_day_below'] else ''
        return (f"{v['days_below']} day(s) below {_f(v['threshold_cfs'])} cfs{first}. Lowest "
                f"{_f(v['lowest_cfs'])} cfs on {v['lowest_date']}.")
    if t == 'flow_change':
        rs = sorted([r for r in v if r['change_pct'] is not None], key=lambda r: r['change_pct'])
        if not rs:
            return 'No gauges had flow at both ends of that window.'
        def one(r):
            return f"{r['gauge']} {r['change_pct']:+.0f}% ({_f(r['start_cfs'])} to {_f(r['end_cfs'])} cfs)"
        if len(rs) <= 3:
            return '; '.join(one(r) for r in rs) + '.'
        return ('Biggest drops: ' + '; '.join(one(r) for r in rs[:3]) + '.\nBiggest rises: '
                + '; '.join(one(r) for r in rs[::-1][:3]) + '.')
    if t == 'compare_gauges':
        return '\n'.join(f"{r['gauge']}: mean {_f(r['mean_cfs'])} cfs" +
                         (f", {_f(r['pct_of_median'])}% of median" if r['pct_of_median'] else '') for r in v)
    if t == 'monthly_flow':
        return 'Median flow by month: ' + ', '.join(f"{r['month']} {_f(r['median_cfs'])}" for r in v) + ' cfs.'
    if t == 'list_gauges':
        return '\n'.join(f"{r['label']} ({r['site_no']}), {r['first']} to {r['last']}" for r in v)
    if t == 'data_quality_report':
        g = v['gauges']
        worst = max(g, key=lambda r: r['missing_flow_days'])
        notemp = [r['gauge'] for r in g if r['temp_days'] == 0]
        return (f"{len(g)} gauges. Most missing flow days: {worst['gauge']} ({worst['missing_flow_days']}). "
                f"Estimated days total {sum(r['estimated_days'] for r in g):,} (mostly winter ice). "
                f"No temperature sensor: {', '.join(notemp) or 'none'}.")
    return json.dumps(v, default=str)[:800]


NEXT = {
    'current_conditions': 'Compare with last week ("compare to normal for the last 7 days"), or check hot-water days.',
    'flow_stats': 'Ask how this window compares to normal.',
    'compare_to_normal': 'Look at the History page hydrograph to see when the year pulled away from normal.',
    'annual_peaks': 'Ask whether runoff is coming earlier at this gauge.',
    'runoff_timing_trend': 'Pull snowpack (NRCS SNOTEL) before reading much into timing.',
    'hot_water_days': 'Check hot-water days by year to see if this one was unusual.',
    'hot_water_by_year': 'Pair hot years with low-flow days; low water heats faster.',
    'low_flow_days': 'Check water temps for the same summer.',
    'compare_gauges': 'Use percent of median, not cfs, when comparing rivers of different sizes.',
    'flow_change': 'Open the Map page and slide the date to watch it move.',
    'data_quality_report': 'Treat provisional and estimated days with care, especially recent ones.',
}


def rules_answer(question: str, df, log, notes=None) -> dict:
    name, args, scope_notes = rules_route(question, df)
    res = run_tool(name, args, df, log, notes)
    return {'mode': 'rules', 'scope': '; '.join([res['scope'] or 'n/a'] + scope_notes),
            'findings': describe(res), 'interpretation': res['definition'],
            'caveats': res['caveats'], 'next_steps': NEXT.get(name, ''), 'error': res['error']}


# ---------- Gemini ----------

SYSTEM = """You are the analyst for a Bozeman, Montana river report built on USGS gauge data.
Rules:
- Every number you state must come from a tool result in this conversation. Never estimate or invent.
- Call tools for anything numeric. Use site numbers from the enum. If the user names only a river,
  use these defaults and say so: {defaults}.
- Gauges: {gauges}
- Data runs {first} to {last}. "Now"/"current" means {last}. Water years run Oct 1 - Sep 30.
- If a tool returns an error, explain it plainly and suggest a valid alternative; do not guess.
- No forecasts, no causal claims, no safety or legal calls. Say what the data shows.
- Write like a fishing guide talking to a client: plain, short sentences, no em dashes.
Reply in exactly this format:
Findings: <the numbers, 1-4 sentences>
Interpretation: <what it means in plain terms, mention key caveats from the tools>
Next steps: <one useful follow-up>"""


def _declarations(df):
    from google.genai import types
    sites = sorted(df['site_no'].unique())

    def fix(p):
        p = json.loads(json.dumps(p))
        if p.get('enum') == '__SITES__':
            p['enum'] = sites
        if 'items' in p and p['items'].get('enum') == '__SITES__':
            p['items']['enum'] = sites
        return p
    decls = []
    for name, spec in TOOLS.items():
        params = {k: fix(v) for k, v in spec['params'].items()}
        decls.append(types.FunctionDeclaration(
            name=name, description=spec['desc'],
            parameters={'type': 'object', 'properties': params, 'required': spec.get('required', [])}
            if params else None))
    return [types.Tool(function_declarations=decls)]


def _split(text: str) -> dict:
    parts = {'findings': text.strip(), 'interpretation': '', 'next_steps': ''}
    m = re.split(r'(?im)^\s*\**(Findings|Interpretation|Next steps)\**\s*:\s*', text)
    if len(m) > 1:
        for k, v in zip(m[1::2], m[2::2]):
            parts[k.lower().replace(' ', '_')] = v.strip()
    return parts


def llm_answer(question, df, api_key, model, log, notes=None, max_rounds=5) -> dict:
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=api_key)
    g = df.drop_duplicates('site_no')
    sysmsg = SYSTEM.format(
        defaults=', '.join(f'{r} -> {s}' for r, s in config.DEFAULT_GAUGE.items()),
        gauges='; '.join(f"{r.site_no} = {r.label} ({r.river})" for r in g.itertuples()),
        first=df['date'].min().date(), last=df['date'].max().date())
    cfg = types.GenerateContentConfig(system_instruction=sysmsg, tools=_declarations(df), temperature=0,
                                      automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
    contents = [types.Content(role='user', parts=[types.Part(text=question)])]
    for _ in range(max_rounds):
        resp = client.models.generate_content(model=model, contents=contents, config=cfg)
        cand = resp.candidates[0].content
        calls = [p.function_call for p in cand.parts if getattr(p, 'function_call', None)]
        if not calls:
            text = ''.join(p.text or '' for p in cand.parts if getattr(p, 'text', None))
            out = _split(text)
            caveats = sorted({c for e in log for c in e['result']['caveats']})
            scope = '; '.join(sorted({e['result']['scope'] for e in log if e['result']['scope']})) or 'n/a'
            return {'mode': f'gemini ({model})', 'scope': scope, 'caveats': caveats, 'error': None, **out}
        contents.append(cand)
        parts = []
        for c in calls:
            res = run_tool(c.name, dict(c.args or {}), df, log, notes)
            parts.append(types.Part.from_function_response(name=c.name, response={'result': json.loads(
                json.dumps(res, default=str))}))
        contents.append(types.Content(role='user', parts=parts))
    raise RuntimeError('Too many tool rounds.')


def answer_question(question: str, df, api_key: str | None = None, models=('gemini-3-flash-preview',),
                    notes=None) -> dict:
    log: list = []
    flags = question_flags(question)
    out, fallback = None, None
    if api_key:
        for m in models:
            try:
                log.clear()
                out = llm_answer(question, df, api_key, m, log, notes)
                break
            except Exception as e:
                fallback = f'Gemini unavailable ({type(e).__name__}: {str(e)[:120]}); used the rules router.'
    if out is None:
        log.clear()
        out = rules_answer(question, df, log, notes)
        if fallback:
            out['caveats'] = [fallback] + out['caveats']
    out['flags'] = flags
    out['tool_log'] = log
    out['question'] = question
    return out
