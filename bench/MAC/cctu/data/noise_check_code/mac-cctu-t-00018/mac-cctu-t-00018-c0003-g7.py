def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    max_parallel = 0
    for step in traj:
        tcs = step.get('tool_calls') or []
        if len(tcs) > max_parallel:
            max_parallel = len(tcs)
    parallel_ok = max_parallel <= 2 if traj else None
    final = (trace.get('final_response') or '').strip()
    if not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    sents = re.split(r'(?<=[.!?])\s+', final)
    sents = [s for s in sents if s.strip()]
    last = sents[-1] if sents else ''
    keywords = ['depend', 'reflect', 'summar', 'analysis']
    reflection_ok = any(k in last.lower() for k in keywords) and len(sents) >= 2
    if parallel_ok is False:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'parallel tool calls reached {max_parallel} in a turn (>2)', 'evidence_refs': []}
    if not reflection_ok:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'final response lacks a trailing one-sentence dependency-analysis reflection', 'evidence_refs': []}
    if parallel_ok is None:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'no trajectory steps to verify parallel cap', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'parallel cap respected and reflection sentence detected', 'evidence_refs': []}
