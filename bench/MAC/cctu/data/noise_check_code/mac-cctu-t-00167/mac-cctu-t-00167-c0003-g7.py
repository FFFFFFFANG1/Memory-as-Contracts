def evaluate(trace):
    trajectory = trace.get('trajectory') or []
    violations = []
    total_calls = 0
    for i, step in enumerate(trajectory):
        tcs = step.get('tool_calls') or []
        total_calls += len(tcs)
        if len(tcs) > 1:
            violations.append(i)
    if total_calls == 0:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls in trajectory', 'evidence_refs': []}
    if violations:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Parallel tool calls found in steps {violations}', 'evidence_refs': violations}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'All tool calls were serialized one at a time', 'evidence_refs': []}
