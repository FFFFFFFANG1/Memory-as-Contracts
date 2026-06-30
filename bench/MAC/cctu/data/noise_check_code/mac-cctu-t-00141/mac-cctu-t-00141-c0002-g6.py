def evaluate(trace):
    traj = trace.get('trajectory') or []
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found.', 'evidence_refs': []}
    if len(calls) == 1:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'Only one tool call; batching trivially satisfied.', 'evidence_refs': []}
    # Count tool calls per assistant step/iteration
    step_counts = []
    for step in traj:
        tcs = step.get('tool_calls') if isinstance(step, dict) else None
        if tcs:
            step_counts.append(len(tcs))
    if not step_counts:
        # fall back to iteration field on flat calls
        iters = {}
        for c in calls:
            k = c.get('iteration', c.get('index'))
            iters[k] = iters.get(k, 0) + 1
        step_counts = list(iters.values())
    steps_with_calls = [n for n in step_counts if n > 0]
    if len(steps_with_calls) <= 1:
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'All {len(calls)} tool calls issued in a single batched turn.', 'evidence_refs': []}
    if max(steps_with_calls) == 1:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Tool calls spread sequentially across {len(steps_with_calls)} turns with no batching.', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Tool calls span {len(steps_with_calls)} turns (counts={step_counts}); not all issued in one batched interaction.', 'evidence_refs': []}
