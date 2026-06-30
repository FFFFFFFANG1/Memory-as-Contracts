def evaluate(trace):
    traj = trace.get('trajectory') or []
    parallel_steps = []
    total_tool_steps = 0
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if tcs:
            total_tool_steps += 1
            if len(tcs) > 1:
                parallel_steps.append({'step_index': i, 'count': len(tcs)})
    if total_tool_steps == 0:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls observed in trajectory.', 'evidence_refs': []}
    if parallel_steps:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Found {len(parallel_steps)} step(s) issuing multiple tool calls in parallel instead of sequentially.', 'evidence_refs': parallel_steps}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'All {total_tool_steps} tool-calling step(s) issued exactly one tool call.', 'evidence_refs': []}
