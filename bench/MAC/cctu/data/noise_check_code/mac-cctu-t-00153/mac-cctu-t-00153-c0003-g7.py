def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls in trajectory.', 'evidence_refs': []}
    names = [c.get('name') for c in calls]
    if 'city_reputation_identifier' not in names:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'city_reputation_identifier not invoked; cannot determine whether city ambiguity existed.', 'evidence_refs': []}
    first = names[0]
    idx = names.index('city_reputation_identifier')
    if first == 'city_reputation_identifier':
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'city_reputation_identifier was the first tool called.', 'evidence_refs': [{'tool_index': calls[0].get('index'), 'name': first}]}
    return {'observed_followed': False, 'confidence': 'high', 'reason': f'city_reputation_identifier appeared at position {idx} after other tools: {names[:idx]}.', 'evidence_refs': [{'tool_index': calls[i].get('index'), 'name': names[i]} for i in range(idx+1)]}
