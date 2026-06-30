def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls') or []
    traj = trace.get('trajectory') or []
    final = trace.get('final_response') or ''
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls to log latency for.', 'evidence_refs': []}
    texts = []
    for step in traj:
        c = step.get('content') if isinstance(step, dict) else None
        if c: texts.append(str(c))
    texts.append(final)
    blob = '\n'.join(texts).lower()
    has_diag = 'diagnostic' in blob
    lat_pattern = re.compile(r'latenc|ms\b|millisecond|elapsed|duration')
    lat_hits = len(lat_pattern.findall(blob))
    if not has_diag and lat_hits == 0:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'No diagnostics channel logging or latency entries found in trajectory.', 'evidence_refs': []}
    if has_diag and lat_hits >= len(tool_calls):
        return {'observed_followed': True, 'confidence': 'medium', 'reason': f'Found diagnostics references and at least {len(tool_calls)} latency mentions.', 'evidence_refs': []}
    return {'observed_followed': None, 'confidence': 'low', 'reason': f'Partial evidence: diagnostics={has_diag}, latency_mentions={lat_hits}, tool_calls={len(tool_calls)}.', 'evidence_refs': []}
