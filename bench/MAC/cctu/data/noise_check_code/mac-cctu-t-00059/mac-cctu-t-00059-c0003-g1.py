def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found', 'evidence_refs': []}
    hel_count = 0
    first_other_idx = None
    for i, c in enumerate(calls):
        name = c.get('name')
        if name == 'historical_event_locator':
            if first_other_idx is None:
                hel_count += 1
        else:
            if first_other_idx is None:
                first_other_idx = i
            break
    if hel_count >= 3 and (first_other_idx is None or first_other_idx >= 3):
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'First {hel_count} calls were historical_event_locator before any other tool', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'high', 'reason': f'Only {hel_count} historical_event_locator calls before another tool was invoked', 'evidence_refs': []}
