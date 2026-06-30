def evaluate(trace):
    traj = trace.get('trajectory') or []
    calls = trace.get('tool_calls') or []
    total = len(calls)
    parallel_turn = None
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if len(tcs) > 1:
            parallel_turn = i
            break
    if total > 4:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Total tool calls {total} exceeds 4.', 'evidence_refs': []}
    if parallel_turn is not None:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Multiple tool calls in turn {parallel_turn}.', 'evidence_refs': []}
    if total == 0 and not traj:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No trajectory evidence.', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'{total} sequential tool calls, none parallel.', 'evidence_refs': []}
