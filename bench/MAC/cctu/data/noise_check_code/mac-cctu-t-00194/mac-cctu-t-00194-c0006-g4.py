def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls', 'evidence_refs': []}
    def is_fail(c):
        r = c.get('result')
        if r is None or r == '' or r == {} or r == []:
            return True
        s = str(r).lower()
        return any(k in s for k in ['error','failed','failure','exception','not found','no result','empty','none'])
    # group consecutive calls to same tool
    groups = {}
    for c in calls:
        groups.setdefault(c.get('name'), []).append(c)
    failures = []
    abandoned_without_retry = []
    for name, lst in groups.items():
        for i, c in enumerate(lst):
            if is_fail(c):
                failures.append((name, i, c))
    if not failures:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no failed/empty tool calls observed', 'evidence_refs': []}
    violations = []
    evidence = []
    for name, idx, c in failures:
        lst = groups[name]
        # retries are subsequent calls to same tool
        retries = lst[idx+1:]
        # only count up to 3 retries window
        retry_window = retries[:3]
        any_success = any(not is_fail(r) for r in retry_window)
        if any_success:
            continue
        # if no retries at all and call failed -> abandoned without retry
        if len(retry_window) == 0:
            violations.append(f'{name} failed at idx {c.get("index")} with no retry')
            evidence.append(c.get('index'))
            continue
        # check progressive simplification: args length should not grow
        args_seq = [c.get('arguments')] + [r.get('arguments') for r in retry_window]
        sizes = [len(str(a)) if a is not None else 0 for a in args_seq]
        simplified = all(sizes[i+1] <= sizes[i] for i in range(len(sizes)-1))
        if not simplified:
            violations.append(f'{name} retries did not progressively simplify args (sizes={sizes})')
            evidence.append(c.get('index'))
    if violations:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(violations[:3]), 'evidence_refs': evidence[:5]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'failed calls were retried with non-increasing arg complexity or eventually succeeded', 'evidence_refs': []}
