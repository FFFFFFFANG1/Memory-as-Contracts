def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls recorded', 'evidence_refs': []}
    total = len(calls)
    counts = {}
    for c in calls:
        name = c.get('name') or c.get('tool') or ''
        counts[name] = counts.get(name, 0) + 1
    over_total = total > 3
    repeats = {n: k for n, k in counts.items() if k > 1}
    if over_total or repeats:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'total={total}, counts={counts}', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'total={total}, counts={counts}', 'evidence_refs': []}
