def evaluate(trace):
    traj = trace.get('trajectory') or []
    if not traj:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no trajectory', 'evidence_refs': []}
    first = None
    for step in traj:
        tcs = step.get('tool_calls') or []
        if tcs:
            first = step
            break
    if first is None:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no tool calls in trajectory', 'evidence_refs': []}
    tcs = first.get('tool_calls') or []
    if len(tcs) < 3:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'opening turn had {len(tcs)} tool calls, need >=3', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'opening turn dispatched {len(tcs)} parallel tool calls', 'evidence_refs': []}
