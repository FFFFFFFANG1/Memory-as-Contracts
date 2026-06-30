def evaluate(trace):
    calls = trace.get('tool_calls', []) or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls recorded', 'evidence_refs': []}
    total = len(calls)
    # group by iteration to detect parallel calls
    groups = {}
    for c in calls:
        it = c.get('iteration')
        groups.setdefault(it, []).append(c.get('name'))
    parallel_ok = False
    for it, names in groups.items():
        if 'historical_event_tool' in names and 'historical_event_information_tool' in names:
            parallel_ok = True
            break
    count_ok = total >= 5
    followed = count_ok and parallel_ok
    reason = f'tool_calls={total} (>=5: {count_ok}), parallel hist tools: {parallel_ok}'
    return {'observed_followed': bool(followed), 'confidence': 'high', 'reason': reason, 'evidence_refs': []}
