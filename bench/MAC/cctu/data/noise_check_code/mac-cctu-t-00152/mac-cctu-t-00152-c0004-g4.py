def evaluate(trace):
    tools = ['architectural_wonder_locator','author_theme_explorer','book_info_retriever','historical_event_finder','historical_fact_retriever','historical_landmark_identifier','historical_landmark_locator','literary_work_finder','space_mission_historian']
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls','evidence_refs':[]}
    counts = {t:0 for t in tools}
    for c in calls:
        n = c.get('name')
        if n in counts:
            counts[n] += 1
    # check parallel: multiple tool_calls in a single trajectory step
    parallel_violation = False
    parallel_refs = []
    for i, step in enumerate(trace.get('trajectory') or []):
        tcs = step.get('tool_calls') or []
        if len(tcs) > 1:
            parallel_violation = True
            parallel_refs.append(f'step {i} has {len(tcs)} parallel calls')
    over = [t for t,c in counts.items() if c > 1]
    missing = [t for t,c in counts.items() if c == 0]
    if parallel_violation:
        return {'observed_followed': False,'confidence':'high','reason':'parallel tool calls detected: '+'; '.join(parallel_refs),'evidence_refs':parallel_refs}
    if over:
        return {'observed_followed': False,'confidence':'high','reason':'tools called more than once: '+','.join(over),'evidence_refs':over}
    if missing:
        return {'observed_followed': None,'confidence':'low','reason':'some tools not exercised (may be outside calibration phase): '+','.join(missing),'evidence_refs':missing}
    return {'observed_followed': True,'confidence':'high','reason':'each tool used exactly once with no parallel bundling','evidence_refs':[]}
