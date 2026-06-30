def evaluate(trace):
    from collections import Counter
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no tool calls observed', 'evidence_refs': []}
    total = len(tool_calls)
    reasons = []
    if total > 20:
        reasons.append('total tool calls {} exceeds 20'.format(total))
    per_turn = Counter()
    for c in tool_calls:
        key = c.get('iteration')
        if key is None:
            key = c.get('turn')
        if key is None:
            key = c.get('index')
        per_turn[key] += 1
    over = [(k, v) for k, v in per_turn.items() if v > 4]
    if over:
        reasons.append('turn(s) exceed 4 parallel calls: ' + str(over))
    if reasons:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'total={} <=20 and per-turn parallelism <=4'.format(total), 'evidence_refs': []}
