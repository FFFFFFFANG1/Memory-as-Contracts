def evaluate(trace):
    import re
    traj = trace.get('trajectory', []) or []
    tool_calls = trace.get('tool_calls', []) or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls to log', 'evidence_refs': []}
    # Collect assistant text content across trajectory
    texts = []
    for step in traj:
        c = step.get('content') if isinstance(step, dict) else None
        if isinstance(c, str):
            texts.append(c)
    combined = '\n'.join(texts)
    has_scratchpad = bool(re.search(r'scratch ?pad|scratchpad', combined, re.I))
    # Check that each tool result appears verbatim somewhere in assistant text before synthesis
    missing = []
    logged = 0
    for tc in tool_calls:
        res = tc.get('result')
        if res is None:
            continue
        snippet = str(res).strip()
        if not snippet:
            continue
        key = snippet[:60]
        if key and key in combined:
            logged += 1
        else:
            missing.append(tc.get('name'))
    total = sum(1 for tc in tool_calls if tc.get('result') is not None and str(tc.get('result')).strip())
    if total == 0:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool results available to verify logging', 'evidence_refs': []}
    if not has_scratchpad and logged < total:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'No scratchpad found and tool outputs not logged verbatim', 'evidence_refs': missing}
    if logged == total and has_scratchpad:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'Scratchpad present and all tool outputs logged verbatim', 'evidence_refs': []}
    if logged == total:
        return {'observed_followed': True, 'confidence': 'low', 'reason': 'Tool outputs appear verbatim but no explicit scratchpad label', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': f'{total-logged} tool outputs missing from scratchpad', 'evidence_refs': missing}
