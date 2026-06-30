def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls found in trajectory', 'evidence_refs': []}
    names = [c.get('name') for c in calls if c.get('name')]
    distinct = []
    for n in names:
        if n not in distinct:
            distinct.append(n)
    total = len(names)
    if total < 3:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'only {total} tool call(s); cannot cross-verify each result with >=2 independent tools', 'evidence_refs': names}
    if len(distinct) < 3:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'only {len(distinct)} distinct tool(s) used: {distinct}; cross-verification requires at least 3 independent tools', 'evidence_refs': distinct}
    counts = {n: names.count(n) for n in distinct}
    singletons = [n for n,c in counts.items() if c == 1]
    if singletons and len(distinct) >= 3 and total >= len(distinct) + 2:
        return {'observed_followed': True, 'confidence': 'low', 'reason': f'used {len(distinct)} distinct tools with {total} calls; cross-verification plausible but cannot confirm per-result corroboration', 'evidence_refs': [counts]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'used {len(distinct)} distinct tools across {total} calls consistent with cross-verification', 'evidence_refs': [counts]}
