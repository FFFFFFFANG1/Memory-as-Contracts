def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls observed', 'evidence_refs': []}
    iters = set()
    for c in calls:
        it = c.get('iteration')
        if it is None:
            it = c.get('turn')
        iters.add(it)
    if None in iters and len(iters) == 1:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'Iteration metadata missing; cannot confirm single parallel turn', 'evidence_refs': []}
    if len(iters) == 1:
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'All {len(calls)} tool calls executed in a single turn (iteration={next(iter(iters))})', 'evidence_refs': [str(i) for i in range(len(calls))]}
    return {'observed_followed': False, 'confidence': 'high', 'reason': f'Tool calls spread across {len(iters)} turns: {sorted(i for i in iters if i is not None)}', 'evidence_refs': [str(i) for i in range(len(calls))]}
