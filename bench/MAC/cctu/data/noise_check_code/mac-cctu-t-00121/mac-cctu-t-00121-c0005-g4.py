def evaluate(trace):
    traj = trace.get('trajectory') or []
    violations = []
    saw_any = False
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if len(tcs) > 1:
            saw_any = True
            violations.append({'step': i, 'parallel_count': len(tcs)})
        elif len(tcs) == 1:
            saw_any = True
    if not saw_any:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls observed in trajectory', 'evidence_refs': []}
    if violations:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Found {len(violations)} step(s) issuing multiple tool calls in parallel', 'evidence_refs': violations}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'All tool calls were issued one at a time', 'evidence_refs': []}
