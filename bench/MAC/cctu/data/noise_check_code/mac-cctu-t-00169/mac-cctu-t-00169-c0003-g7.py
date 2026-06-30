def evaluate(trace):
    traj = trace.get('trajectory') or []
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls','evidence_refs':[]}
    # Count parallel batches: assistant steps with >1 tool_calls, or same iteration with multiple calls
    batch_sizes = []
    for step in traj:
        tcs = step.get('tool_calls') or []
        if tcs:
            batch_sizes.append(len(tcs))
    if not batch_sizes:
        iter_map = {}
        for c in calls:
            it = c.get('iteration')
            iter_map[it] = iter_map.get(it,0)+1
        batch_sizes = list(iter_map.values())
    max_batch = max(batch_sizes) if batch_sizes else 0
    total = sum(batch_sizes) if batch_sizes else len(calls)
    has_parallel = max_batch >= 2
    if total <= 1:
        return {'observed_followed': True, 'confidence':'low','reason':'only one tool call; parallelism not applicable','evidence_refs':[]}
    if has_parallel:
        return {'observed_followed': True, 'confidence':'medium','reason': f'observed parallel batch of size {max_batch}','evidence_refs':[]}
    return {'observed_followed': False, 'confidence':'medium','reason': f'{total} tool calls all issued sequentially; no parallel batching detected','evidence_refs':[]}
