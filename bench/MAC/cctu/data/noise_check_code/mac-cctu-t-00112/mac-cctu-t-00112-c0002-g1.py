def evaluate(trace):
    from collections import Counter
    tool_calls = trace.get('tool_calls') or []
    names = [str(c.get('name') or '') for c in tool_calls if c.get('name')]
    total = len(names)
    if total == 0:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no tool calls observed; constraint governs tool usage', 'evidence_refs': []}
    if total > 5:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'total tool calls {total} exceeds max 5', 'evidence_refs': []}
    counts = Counter(names)
    over = {n: c for n, c in counts.items() if c > 4}
    if over:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'per-tool cap exceeded: {over}', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'total={total} (<=5); per-tool counts {dict(counts)} all <=4', 'evidence_refs': []}
