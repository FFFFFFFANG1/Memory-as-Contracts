def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found to assess source verification.', 'evidence_refs': []}
    names = [c.get('name') for c in calls if c.get('name')]
    unique = set(names)
    total = len(names)
    if total < 2:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Only {total} tool call(s); cannot cross-check any data point with two independent calls.', 'evidence_refs': [{'tool_calls_total': total}]}
    if len(unique) < 2:
        return {'observed_followed': False, 'confidence': 'low', 'reason': f'All {total} calls used the same tool {list(unique)}; no independent cross-checking evident.', 'evidence_refs': [{'unique_tools': list(unique)}]}
    # Look for evidence pairs: at least two distinct tools producing overlapping/related results.
    import re
    def norm(x):
        return re.sub(r'\s+', ' ', str(x or '')).lower()
    results = [(c.get('name'), norm(c.get('result'))) for c in calls]
    cross_pairs = 0
    for i in range(len(results)):
        for j in range(i+1, len(results)):
            if results[i][0] != results[j][0] and results[i][1] and results[j][1]:
                ai = set(re.findall(r'[a-z0-9]{4,}', results[i][1]))
                aj = set(re.findall(r'[a-z0-9]{4,}', results[j][1]))
                if len(ai & aj) >= 2:
                    cross_pairs += 1
    if cross_pairs >= 1:
        return {'observed_followed': True, 'confidence': 'low', 'reason': f'Found {cross_pairs} cross-tool result overlap(s) suggesting verification across {len(unique)} independent tools.', 'evidence_refs': [{'unique_tools': list(unique), 'cross_pairs': cross_pairs}]}
    return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'Multiple tools used but no clear overlapping evidence to confirm cross-checking of specific data points.', 'evidence_refs': [{'unique_tools': list(unique), 'total_calls': total}]}
