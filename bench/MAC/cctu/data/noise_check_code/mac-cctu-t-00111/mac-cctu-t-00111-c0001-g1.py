def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls', []) or []
    traj = trace.get('trajectory', []) or []
    allowed = 'unified_distance_calculator'
    used = [tc.get('name') for tc in tool_calls]
    if not used:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls observed.', 'evidence_refs': []}
    forbidden = [n for n in used if n and n != allowed]
    if forbidden:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Used non-allowed tools: {sorted(set(forbidden))}', 'evidence_refs': forbidden}
    latlon_re = re.compile(r'-?\d{1,3}\.\d+\s*[,\s]\s*-?\d{1,3}\.\d+')
    coord_word_re = re.compile(r'lat(itude)?|lon(gitude)?', re.I)
    steps = []
    for s in traj:
        c = s.get('content') or ''
        if c.strip():
            steps.append(c)
    if not steps:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No reasoning steps with content.', 'evidence_refs': []}
    missing = []
    for i, c in enumerate(steps):
        if not (latlon_re.search(c) or coord_word_re.search(c)):
            missing.append(i)
    if missing:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Reasoning steps lacking lat/lon references at indices {missing}.', 'evidence_refs': missing}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Only unified_distance_calculator used; all reasoning steps include lat/lon references.', 'evidence_refs': used}
