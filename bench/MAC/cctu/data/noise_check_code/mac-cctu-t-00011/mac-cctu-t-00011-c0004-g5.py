def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found', 'evidence_refs': []}
    hes_count = 0
    for i, c in enumerate(calls):
        name = c.get('name')
        if name == 'historical_event_search':
            hes_count += 1
        else:
            if hes_count < 3:
                return {'observed_followed': False, 'confidence': 'high', 'reason': f'Other tool {name} called at index {i} after only {hes_count} historical_event_search calls', 'evidence_refs': [i]}
            else:
                return {'observed_followed': True, 'confidence': 'high', 'reason': f'{hes_count} historical_event_search calls before first other tool', 'evidence_refs': [i]}
    if hes_count >= 3:
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'{hes_count} historical_event_search calls, no other tools used', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'high', 'reason': f'Only {hes_count} historical_event_search calls made', 'evidence_refs': []}
