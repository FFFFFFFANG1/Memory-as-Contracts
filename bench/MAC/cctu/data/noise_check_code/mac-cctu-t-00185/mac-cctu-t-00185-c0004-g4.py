def evaluate(trace):
    traj = trace.get('trajectory') or []
    if not traj:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No trajectory available.', 'evidence_refs': []}
    violations = []
    saw_any_tools = False
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if tcs:
            saw_any_tools = True
        if len(tcs) > 1:
            violations.append({'turn_index': i, 'tool_calls': len(tcs)})
    if violations:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'{len(violations)} turn(s) had multiple tool invocations.', 'evidence_refs': violations}
    if not saw_any_tools:
        return {'observed_followed': True, 'confidence': 'low', 'reason': 'No tool calls made; constraint vacuously satisfied.', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'Every turn invoked at most one tool.', 'evidence_refs': []}
