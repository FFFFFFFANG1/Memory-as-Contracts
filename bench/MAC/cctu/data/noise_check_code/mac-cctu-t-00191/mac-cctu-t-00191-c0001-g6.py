def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found', 'evidence_refs': []}
    turns = {}
    for c in calls:
        t = c.get('iteration')
        if t is None:
            t = c.get('turn', 0)
        turns.setdefault(t, []).append(c)
    bad = []
    for t, lst in turns.items():
        lst_sorted = sorted(lst, key=lambda x: x.get('index', 0))
        first = lst_sorted[0].get('name')
        if first != 'historical_event_locator':
            bad.append({'turn': t, 'first_tool': first})
    if bad:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Turns where first tool was not historical_event_locator: {bad}', 'evidence_refs': bad}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'historical_event_locator is first tool in every turn', 'evidence_refs': list(turns.keys())}
