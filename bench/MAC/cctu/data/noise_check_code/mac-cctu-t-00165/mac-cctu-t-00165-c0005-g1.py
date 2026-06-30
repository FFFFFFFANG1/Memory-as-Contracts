def evaluate(trace):
    trace = trace or {}
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no tool calls observed; constraint requires tool usage', 'evidence_refs': []}
    count = 0
    for call in tool_calls:
        name = str((call or {}).get('name') or '')
        if name == 'species_record_locator':
            count += 1
    evidence = [{'tool': 'species_record_locator', 'count': count}]
    if count > 2:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'species_record_locator called {count} times, exceeds maximum 2', 'evidence_refs': evidence}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'species_record_locator called {count} times (<=2)', 'evidence_refs': evidence}
