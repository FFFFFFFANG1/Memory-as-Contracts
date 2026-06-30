def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls', 'evidence_refs': []}
    groups = {}
    for c in calls:
        it = c.get('iteration')
        if it is None:
            it = c.get('index')
        groups.setdefault(it, []).append(c)
    bad = []
    good = 0
    for it, gs in groups.items():
        if len(gs) != 3:
            bad.append({'iteration': it, 'count': len(gs)})
        else:
            good += 1
    if bad:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Turns not batched as exactly 3 parallel calls: {bad}', 'evidence_refs': [str(b) for b in bad]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'All {good} turn(s) had exactly 3 parallel calls', 'evidence_refs': []}
