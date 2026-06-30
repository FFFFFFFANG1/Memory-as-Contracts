def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls', 'evidence_refs': []}
    by_iter = {}
    for c in calls:
        it = c.get('iteration')
        by_iter.setdefault(it, []).append(c.get('name'))
    iters = sorted(by_iter.keys(), key=lambda x: (x is None, x))
    distinct_tools = set(c.get('name') for c in calls)
    if len(distinct_tools) <= 1:
        return {'observed_followed': True, 'confidence': 'low', 'reason': 'only one distinct tool used; parallelism not applicable', 'evidence_refs': []}
    parallel_batches = [i for i, names in by_iter.items() if len(names) > 1]
    sequential_distinct = []
    prev = None
    for i in iters:
        names = by_iter[i]
        if len(names) == 1:
            n = names[0]
            if prev is not None and n != prev:
                sequential_distinct.append((prev, n))
            prev = n
        else:
            prev = names[-1]
    if parallel_batches and not sequential_distinct:
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'distinct tools dispatched in parallel batches at iterations {parallel_batches}', 'evidence_refs': [str(parallel_batches)]}
    if sequential_distinct and not parallel_batches:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'distinct tools called sequentially across iterations: {sequential_distinct}', 'evidence_refs': [str(sequential_distinct)]}
    if parallel_batches and sequential_distinct:
        return {'observed_followed': False, 'confidence': 'low', 'reason': f'some parallel batches present but also sequential distinct calls: {sequential_distinct}', 'evidence_refs': [str(sequential_distinct), str(parallel_batches)]}
    return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'unable to determine independence of calls', 'evidence_refs': []}
