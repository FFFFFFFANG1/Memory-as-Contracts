def evaluate(trace):
    traj = trace.get('trajectory') or []
    violations = []
    steps_with_calls = 0
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if not tcs:
            continue
        steps_with_calls += 1
        if len(tcs) != 1:
            violations.append({'step_index': i, 'tool_call_count': len(tcs)})
    if steps_with_calls == 0:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No action steps with tool calls found in trajectory.', 'evidence_refs': []}
    if violations:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Found {len(violations)} action step(s) not issuing exactly one tool call.', 'evidence_refs': violations}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'All {steps_with_calls} action step(s) issued exactly one tool call.', 'evidence_refs': []}
