def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found in trajectory.', 'evidence_refs': []}
    anchor = 'research_location_identifier'
    # Check first call overall
    first = calls[0].get('name')
    if first != anchor:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'First tool call was {first!r}, not {anchor!r}.', 'evidence_refs': [{'index': calls[0].get('index'), 'name': first}]}
    # Check per-iteration (sub-task proxy): first call of each iteration must be the anchor
    seen = {}
    for c in calls:
        it = c.get('iteration')
        if it is None:
            continue
        if it not in seen:
            seen[it] = c
    bad = []
    for it, c in seen.items():
        if c.get('name') != anchor:
            bad.append({'iteration': it, 'name': c.get('name'), 'index': c.get('index')})
    if bad:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Some iterations/sub-tasks did not begin with research_location_identifier.', 'evidence_refs': bad}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'Each observed sub-task/iteration begins with research_location_identifier.', 'evidence_refs': [{'first_tool': first}]}
