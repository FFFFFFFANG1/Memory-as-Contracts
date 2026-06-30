def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls to evaluate.', 'evidence_refs': []}
    iso_re = re.compile(r'\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?')
    # Collect assistant text content across trajectory
    texts = []
    for step in traj:
        c = step.get('content') or ''
        if isinstance(c, str) and c.strip():
            texts.append(c)
    combined = '\n'.join(texts)
    n = len(tool_calls)
    iso_hits = len(iso_re.findall(combined))
    # heuristic: look for a scratchpad/log pattern
    has_scratchpad = bool(re.search(r'scratchpad|log[: ]|justification', combined, re.I))
    if iso_hits >= n and has_scratchpad:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': f'Found {iso_hits} ISO timestamps and scratchpad/justification markers for {n} tool calls.', 'evidence_refs': []}
    if iso_hits == 0 and not has_scratchpad:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'No ISO timestamps or scratchpad/justification entries found between tool calls.', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'low', 'reason': f'Partial logging: {iso_hits} ISO timestamps vs {n} tool calls; scratchpad markers present={has_scratchpad}.', 'evidence_refs': []}
