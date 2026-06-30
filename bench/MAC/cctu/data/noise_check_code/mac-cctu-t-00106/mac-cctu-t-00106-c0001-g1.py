def evaluate(trace):
    tcs = trace.get('tool_calls', []) or []
    target = {'marine_biology_facts','factual_information_retriever'}
    if not tcs:
        return {'observed_followed': False, 'confidence':'high','reason':'no tool calls','evidence_refs':[]}
    groups = {}
    for tc in tcs:
        it = tc.get('iteration')
        if it is None:
            it = tc.get('index')
        groups.setdefault(it, []).append(tc)
    best = 0
    best_it = None
    for it, calls in groups.items():
        if len(calls) < 2:
            continue
        c = sum(1 for x in calls if x.get('name') in target)
        if c > best:
            best = c
            best_it = it
    if best >= 5:
        return {'observed_followed': True, 'confidence':'high','reason': f'{best} parallel target calls in iteration {best_it}','evidence_refs':[]}
    return {'observed_followed': False, 'confidence':'medium','reason': f'max parallel target calls = {best}','evidence_refs':[]}
