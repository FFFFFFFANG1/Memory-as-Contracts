def evaluate(trace):
    calls = trace.get('tool_calls') or []
    names = [c.get('name') for c in calls if c.get('name')]
    distinct = set(names)
    if not calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No tool calls; cannot cross-verify.', 'evidence_refs': []}
    if len(distinct) < 2:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Only {len(distinct)} distinct tool(s) used: {sorted(distinct)}.', 'evidence_refs': []}
    # Check that raw outputs appear in scratchpad/trajectory content
    traj = trace.get('trajectory') or []
    content_blob = ''
    for step in traj:
        c = step.get('content')
        if isinstance(c, str):
            content_blob += '\n' + c
    # Heuristic: look for evidence of recording raw outputs
    recorded = 0
    for c in calls:
        res = c.get('result')
        if res is None:
            continue
        token = str(res)[:25].strip()
        if token and token in content_blob:
            recorded += 1
    if recorded < 2:
        return {'observed_followed': None, 'confidence': 'low', 'reason': f'{len(distinct)} distinct tools called but raw outputs not clearly recorded in scratchpad (matched {recorded}).', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'{len(distinct)} distinct tools used and raw outputs appear recorded.', 'evidence_refs': []}
