def evaluate(trace):
    calls = trace.get('tool_calls') or []
    names = [c.get('name') for c in calls]
    cef = sum(1 for n in names if n == 'corporate_event_finder')
    hes = sum(1 for n in names if n == 'historical_event_search')
    total = cef + hes
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found in trace.', 'evidence_refs': []}
    if cef >= 1 and hes >= 1 and total >= 4:
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'Used corporate_event_finder ({cef}) and historical_event_search ({hes}); total {total} >= 4.', 'evidence_refs': names}
    return {'observed_followed': False, 'confidence': 'high', 'reason': f'Need both tools used and >=4 total ownership-verification calls. Got cef={cef}, hes={hes}, total={total}.', 'evidence_refs': names}
