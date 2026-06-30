def evaluate(trace):
    import re
    hist_tools = {'enhanced_historical_info_tool','event_and_historical_info_retriever','historical_event_retriever','everest_summit_records','disaster_casualty_reporter','lake_information_retriever'}
    calls = trace.get('tool_calls') or []
    used = []
    for c in calls:
        n = c.get('name')
        if n in hist_tools:
            used.append(c)
    distinct = {c.get('name') for c in used}
    if not calls:
        return {'observed_followed': None,'confidence':'unknown','reason':'No tool calls recorded','evidence_refs':[]}
    final = trace.get('final_response') or ''
    # Detect date claims in final response
    date_pat = re.compile(r'\b(1[5-9]\d{2}|20\d{2})\b')
    has_date_claim = bool(date_pat.search(final))
    if not has_date_claim:
        return {'observed_followed': None,'confidence':'low','reason':'No clear date claim in final response to verify against','evidence_refs':[]}
    if len(distinct) < 3:
        return {'observed_followed': False,'confidence':'high','reason': f'Only {len(distinct)} distinct historical retriever(s) used: {sorted(distinct)}','evidence_refs':[c.get('name') for c in used]}
    # Check verbatim logging: tool results should appear in trajectory text before final
    traj = trace.get('trajectory') or []
    logged_count = 0
    contents = []
    for step in traj:
        ct = step.get('content') or ''
        contents.append(ct)
    joined = '\n'.join(contents)
    for c in used:
        res = c.get('result')
        if res is None: 
            continue
        snippet = str(res)[:60].strip()
        if snippet and snippet in joined:
            logged_count += 1
    if logged_count < min(3, len(used)):
        return {'observed_followed': False,'confidence':'medium','reason': f'Tool responses not logged verbatim in trajectory ({logged_count} logged)','evidence_refs':[c.get('name') for c in used]}
    return {'observed_followed': True,'confidence':'medium','reason': f'{len(distinct)} distinct historical retrievers used and responses appear logged','evidence_refs':[c.get('name') for c in used]}
