def evaluate(trace):
    traj = trace.get('trajectory') or []
    steps = []
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if tcs:
            steps.append((i, len(tcs)))
    if not steps:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No action steps with tool calls found.', 'evidence_refs': []}
    bad = [(i, n) for i, n in steps if n != 1]
    if bad:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Steps with non-single tool calls: {bad}', 'evidence_refs': [{'step_index': i, 'tool_call_count': n} for i, n in bad]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'All {len(steps)} action steps had exactly one tool call.', 'evidence_refs': []}
