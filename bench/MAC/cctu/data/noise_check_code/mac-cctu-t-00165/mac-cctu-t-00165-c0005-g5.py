def evaluate(trace):
    traj = trace.get('trajectory') or []
    parallel_steps = []
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if len(tcs) > 1:
            parallel_steps.append(i)
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls and not traj:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no trajectory evidence', 'evidence_refs': []}
    if parallel_steps:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'parallel tool invocations detected in steps {parallel_steps}', 'evidence_refs': parallel_steps}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'no parallel tool invocations observed; each step issued at most one tool call', 'evidence_refs': []}
