def evaluate(trace):
    traj = trace.get('trajectory') or []
    turns_with_calls = []
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if tcs:
            turns_with_calls.append((i, len(tcs)))
    if not turns_with_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool-calling turns found in trajectory', 'evidence_refs': []}
    violations = [(i, n) for i, n in turns_with_calls if n != 1]
    if violations:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Turns with non-singleton tool calls: {violations}', 'evidence_refs': [i for i,_ in violations]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'All {len(turns_with_calls)} tool-calling turns contain exactly one tool call', 'evidence_refs': [i for i,_ in turns_with_calls]}
