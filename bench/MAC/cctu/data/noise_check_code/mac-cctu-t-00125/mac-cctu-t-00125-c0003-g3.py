def evaluate(trace):
    traj = trace.get('trajectory') or []
    parallel_steps = []
    saw_tool = False
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if tcs:
            saw_tool = True
        if len(tcs) > 1:
            parallel_steps.append({'step_index': i, 'count': len(tcs)})
    if not saw_tool:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found in trajectory.', 'evidence_refs': []}
    if parallel_steps:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Found {len(parallel_steps)} assistant step(s) issuing multiple tool calls in parallel.', 'evidence_refs': parallel_steps}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'All tool calls were issued one at a time across assistant steps.', 'evidence_refs': []}
