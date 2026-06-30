def evaluate(trace):
    tcs = trace.get('tool_calls') or []
    if not tcs:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls observed', 'evidence_refs': []}
    iters = set()
    for c in tcs:
        it = c.get('iteration')
        if it is None:
            it = c.get('turn')
        iters.add(it)
    traj = trace.get('trajectory') or []
    turns_with_calls = 0
    for step in traj:
        if isinstance(step, dict):
            calls = step.get('tool_calls') or []
            if calls:
                turns_with_calls += 1
    if len(iters) > 1 or turns_with_calls > 1:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'tool calls span multiple turns/iterations ({iters}, turns_with_calls={turns_with_calls}); serial follow-ups present', 'evidence_refs': [str(i) for i in iters]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'all {len(tcs)} tool calls issued in a single parallel batch within one turn', 'evidence_refs': []}
