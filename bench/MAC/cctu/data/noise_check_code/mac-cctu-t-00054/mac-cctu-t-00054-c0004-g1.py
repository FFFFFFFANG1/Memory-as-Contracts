def evaluate(trace):
    allowed = {'historical_location_finder', 'geological_formation_comparator'}
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found', 'evidence_refs': []}
    # Preliminary scoping = the initial phase before any specialized lookup.
    # Identify the boundary as the first call to an allowed tool or the prefix of allowed calls.
    first = calls[0].get('name')
    if first not in allowed:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'First tool call {first!r} is not a preliminary scoping tool', 'evidence_refs': [{'index': calls[0].get('index'), 'name': first}]}
    # Walk through prefix: as long as we are in preliminary phase (only allowed tools used),
    # any non-allowed tool ends the preliminary phase. That's fine, unless an allowed tool appears AFTER
    # specialized ones with no allowed-prefix - already handled. Just verify prefix is non-empty allowed.
    prefix = []
    for c in calls:
        if c.get('name') in allowed:
            prefix.append(c)
        else:
            break
    if len(prefix) == 0:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No preliminary scoping with allowed tools occurred before specialized lookups', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'Preliminary phase used only allowed tools ({len(prefix)} calls) before specialized lookups', 'evidence_refs': [{'index': c.get('index'), 'name': c.get('name')} for c in prefix]}
