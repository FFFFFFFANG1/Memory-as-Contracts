def evaluate(trace):
    import re
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls to evaluate', 'evidence_refs': []}
    num_re = re.compile(r'-?\d+(?:\.\d+)?')
    # map number -> set of tool names that returned it
    num_sources = {}
    per_call_nums = []
    for c in calls:
        name = c.get('name') or ''
        res = c.get('result')
        text = '' if res is None else (res if isinstance(res, str) else str(res))
        nums = set()
        for m in num_re.findall(text):
            try:
                v = float(m)
            except Exception:
                continue
            # ignore trivial small ints often present as ids/indices
            nums.add(v)
            num_sources.setdefault(v, set()).add(name)
        per_call_nums.append((name, nums))
    # consider 'numeric retrievals' as calls returning at least one number
    retrieval_calls = [(n, s) for n, s in per_call_nums if s]
    if not retrieval_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no numeric values found in tool results', 'evidence_refs': []}
    unverified = []
    for name, nums in retrieval_calls:
        # at least one of this call's numbers must be confirmed by a different tool
        confirmed = False
        for v in nums:
            srcs = num_sources.get(v, set())
            if len(srcs) >= 2 and any(s != name for s in srcs):
                confirmed = True
                break
        if not confirmed:
            unverified.append((name, sorted(nums)[:3]))
    if unverified:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'numeric values from {len(unverified)} call(s) not cross-verified by an alternate tool: {unverified[:3]}', 'evidence_refs': []}
    distinct_tools = {n for n, _ in retrieval_calls} | {t for s in num_sources.values() for t in s}
    if len(distinct_tools) < 2:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'only one tool used; no alternate source for verification', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'each numeric retrieval has a matching value from a different tool', 'evidence_refs': []}
