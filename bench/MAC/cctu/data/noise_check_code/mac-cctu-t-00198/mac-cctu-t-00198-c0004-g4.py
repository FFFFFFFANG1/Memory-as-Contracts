def evaluate(trace):
    traj = trace.get('trajectory') or []
    steps_with_calls = []
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if tcs:
            steps_with_calls.append((i, len(tcs)))
    if not steps_with_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool-calling steps found', 'evidence_refs': []}
    bad = [(i, n) for i, n in steps_with_calls if n != 3]
    if bad:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Steps not having exactly 3 parallel calls: {bad}', 'evidence_refs': [{'step_index': i, 'count': n} for i, n in bad]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'All {len(steps_with_calls)} tool-calling steps have exactly 3 parallel calls', 'evidence_refs': [{'step_index': i, 'count': n} for i, n in steps_with_calls]}
