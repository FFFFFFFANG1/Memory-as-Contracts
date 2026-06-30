def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls found', 'evidence_refs': []}
    first = calls[0]
    first_name = first.get('name') or first.get('tool_name') or ''
    if first_name != 'historical_event_date_finder':
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'first tool was {first_name}, not historical_event_date_finder', 'evidence_refs': [{'index': 0, 'name': first_name}]}
    # check if at least one turn (iteration) is dedicated solely to historical_event_date_finder
    by_iter = {}
    for c in calls:
        it = c.get('iteration')
        if it is None:
            it = c.get('index')
        name = c.get('name') or c.get('tool_name') or ''
        by_iter.setdefault(it, []).append(name)
    solo_turn = any(len(set(names)) == 1 and 'historical_event_date_finder' in set(names) for names in by_iter.values())
    if not solo_turn:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'no turn dedicated solely to date verification', 'evidence_refs': [{'iterations': list(by_iter.keys())}]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'date finder called first and a turn was dedicated solely to it', 'evidence_refs': [{'first_tool': first_name}]}
