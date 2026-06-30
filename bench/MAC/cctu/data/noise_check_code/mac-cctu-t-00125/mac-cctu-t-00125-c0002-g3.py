def evaluate(trace):
    traj = trace.get('trajectory') or []
    violations = []
    steps_with_calls = 0
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if len(tcs) > 0:
            steps_with_calls += 1
        if len(tcs) > 1:
            names = [tc.get('name') or (tc.get('function') or {}).get('name') for tc in tcs]
            violations.append({'step_index': i, 'parallel_tool_calls': names})
    if steps_with_calls == 0 and not trace.get('tool_calls'):
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found in trajectory to assess parallel usage.', 'evidence_refs': []}
    if violations:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Found {len(violations)} turn(s) issuing parallel tool calls.', 'evidence_refs': violations}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'Every turn with tool calls issued at most one atomic action.', 'evidence_refs': []}
