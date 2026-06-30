def evaluate(trace):
    import re
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls', 'evidence_refs': []}
    def is_429(r):
        s = str(r) if r is not None else ''
        return '429' in s or 'rate limit' in s.lower() or 'rate-limit' in s.lower()
    first_429_iter = None
    affected_tools = set()
    for c in calls:
        if is_429(c.get('result')):
            it = c.get('iteration')
            if first_429_iter is None or (it is not None and it < first_429_iter):
                first_429_iter = it
            affected_tools.add(c.get('name'))
    if first_429_iter is None:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no 429 errors observed', 'evidence_refs': []}
    # group calls by iteration after the 429
    from_iters = {}
    for c in calls:
        it = c.get('iteration')
        if it is None:
            continue
        if it >= first_429_iter:
            from_iters.setdefault(it, []).append(c)
    parallel_after = []
    for it, group in from_iters.items():
        if it == first_429_iter:
            continue
        if len(group) > 1:
            parallel_after.append(it)
    if parallel_after:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'parallel tool calls in iterations {parallel_after} after 429 at iter {first_429_iter}', 'evidence_refs': [{'iterations': parallel_after}]}
    # check that affected tools were retried serially (each retry in its own iteration)
    retry_iters = [c.get('iteration') for c in calls if c.get('name') in affected_tools and c.get('iteration') is not None and c.get('iteration') > first_429_iter]
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'no parallel execution after 429; retries at {sorted(set(retry_iters))}', 'evidence_refs': [{'first_429_iter': first_429_iter, 'affected_tools': sorted(affected_tools)}]}
