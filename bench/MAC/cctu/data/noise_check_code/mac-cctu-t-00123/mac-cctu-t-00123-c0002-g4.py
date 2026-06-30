def evaluate(trace):
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls present', 'evidence_refs': []}
    # Gather tool calls per assistant step
    steps = []
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if tcs:
            steps.append((i, [tc.get('name') or tc.get('function',{}).get('name') for tc in tcs]))
    if not steps:
        # fallback: group flattened tool_calls by iteration
        by_iter = {}
        for tc in tool_calls:
            it = tc.get('iteration', tc.get('index'))
            by_iter.setdefault(it, []).append(tc.get('name'))
        steps = sorted(by_iter.items())
    if not steps:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'Cannot determine step structure', 'evidence_refs': []}
    total = sum(len(s[1]) for s in steps)
    if total <= 1:
        return {'observed_followed': True, 'confidence': 'low', 'reason': 'Only one tool call; batching trivially satisfied', 'evidence_refs': []}
    first_batch = steps[0][1]
    # If multiple distinct tools used overall but first step is single call -> not batched
    distinct_tools = set()
    for _, names in steps:
        for n in names:
            if n: distinct_tools.add(n)
    if len(first_batch) >= 2:
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'First dispatch contains {len(first_batch)} parallel calls: {first_batch}', 'evidence_refs': [str(first_batch)]}
    if len(distinct_tools) >= 2 and len(first_batch) == 1:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Multiple independent retrievals were issued sequentially rather than batched in parallel; first step had only {first_batch}', 'evidence_refs': [str(steps)]}
    return {'observed_followed': None, 'confidence': 'low', 'reason': 'Could not confirm independence of subtasks', 'evidence_refs': [str(steps)]}
