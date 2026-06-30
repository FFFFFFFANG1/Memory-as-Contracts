def evaluate(trace):
    traj = trace.get('trajectory') or []
    violations = []
    saw_any = False
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if len(tcs) >= 1:
            saw_any = True
        if len(tcs) > 1:
            names = [tc.get('name') for tc in tcs]
            violations.append({'step_index': i, 'tool_calls': names})
    if not saw_any:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls observed in trajectory.', 'evidence_refs': []}
    if violations:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Found {len(violations)} step(s) with parallel tool calls.', 'evidence_refs': violations}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'Each step issued at most one tool call.', 'evidence_refs': []}
