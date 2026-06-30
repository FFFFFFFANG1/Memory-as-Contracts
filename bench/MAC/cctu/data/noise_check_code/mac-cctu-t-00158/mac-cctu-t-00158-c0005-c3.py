def evaluate(trace):
    allowed = {'historical_landmark_data_retriever','historical_site_locator'}
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': False, 'confidence':'high','reason':'no tool calls made','evidence_refs':[]}
    names = [c.get('name') for c in calls]
    bad = [n for n in names if n not in allowed]
    if bad:
        return {'observed_followed': False,'confidence':'high','reason': f'used disallowed tools: {bad}','evidence_refs': names}
    if len(calls) < 3:
        return {'observed_followed': False,'confidence':'high','reason': f'only {len(calls)} calls, need >=3 sequential verification calls','evidence_refs': names}
    # check sequential (not parallel) - indices should be distinct iterations
    iters = [c.get('iteration') for c in calls if c.get('iteration') is not None]
    if iters and len(set(iters)) < 3:
        return {'observed_followed': False,'confidence':'medium','reason':'calls not sufficiently sequential','evidence_refs': iters}
    return {'observed_followed': True,'confidence':'high','reason': f'{len(calls)} allowed sequential calls before response','evidence_refs': names}
