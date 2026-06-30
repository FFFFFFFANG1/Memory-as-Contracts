def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls','evidence_refs':[]}
    # find first 429 error
    first_429_idx = None
    affected_tool = None
    for i, c in enumerate(calls):
        res = c.get('result')
        text = ''
        if isinstance(res, str):
            text = res
        elif isinstance(res, dict):
            text = str(res)
        if '429' in text or 'rate limit' in text.lower() or 'rate-limit' in text.lower():
            first_429_idx = i
            affected_tool = c.get('name')
            break
    if first_429_idx is None:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no 429 error observed; constraint not triggered','evidence_refs':[]}
    # after 429, check no parallel calls (same iteration with >1 call)
    after = calls[first_429_idx+1:]
    if not after:
        return {'observed_followed': None,'confidence':'low','reason':'429 occurred but no subsequent calls to evaluate','evidence_refs':[first_429_idx]}
    iters = {}
    for c in after:
        it = c.get('iteration')
        iters[it] = iters.get(it, 0) + 1
    parallel_after = any(v > 1 for v in iters.values())
    # check retry of affected tool exists
    retried = any(c.get('name') == affected_tool for c in after)
    if parallel_after:
        return {'observed_followed': False,'confidence':'medium','reason':'parallel tool calls occurred after 429 error','evidence_refs':[first_429_idx]}
    if not retried:
        return {'observed_followed': None,'confidence':'low','reason':'no retry of affected tool detected; cannot confirm serial backoff','evidence_refs':[first_429_idx]}
    return {'observed_followed': True,'confidence':'low','reason':'no parallel execution after 429 and affected tool retried serially','evidence_refs':[first_429_idx]}
