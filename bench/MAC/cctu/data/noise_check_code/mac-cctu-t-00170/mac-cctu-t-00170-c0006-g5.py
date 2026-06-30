def evaluate(trace):
    traj = trace.get('trajectory') or []
    turn_sizes = []
    for step in traj:
        tcs = step.get('tool_calls') or []
        if tcs:
            turn_sizes.append(len(tcs))
    if not turn_sizes:
        tcs = trace.get('tool_calls') or []
        if not tcs:
            return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found', 'evidence_refs': []}
        groups = {}
        for c in tcs:
            k = c.get('iteration', c.get('index'))
            groups.setdefault(k, 0)
            groups[k] += 1
        turn_sizes = list(groups.values())
    over = [n for n in turn_sizes if n > 6]
    if over:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'A turn issued {max(over)} parallel tool calls, exceeding 6', 'evidence_refs': []}
    has_parallel = any(n >= 2 for n in turn_sizes)
    if not has_parallel:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'No parallel batches observed; constraint requires parallel batches of exploratory calls', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'Parallel batches observed with max size {max(turn_sizes)} <= 6', 'evidence_refs': []}
