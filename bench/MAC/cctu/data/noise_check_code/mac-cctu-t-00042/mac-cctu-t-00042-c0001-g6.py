def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found in trajectory.', 'evidence_refs': []}
    names = []
    for c in calls:
        n = c.get('name')
        if n and n not in names:
            names.append(n)
    if len(names) >= 2:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': f'At least two independent tools used for verification: {names}.', 'evidence_refs': names}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Only one distinct tool used: {names}. Constraint requires verification across at least two independent tools.', 'evidence_refs': names}
