def evaluate(trace):
    import re
    calls = trace.get('tool_calls', []) or []
    lit_indices = [i for i,c in enumerate(calls) if c.get('name')=='literary_setting_search_v2']
    if not lit_indices:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No literary_setting_search_v2 calls present.', 'evidence_refs': []}
    other_after = any(c.get('name') and c.get('name')!='literary_setting_search_v2' for c in calls[lit_indices[0]+1:])
    if not other_after:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No cross-tool comparison occurred after literary_setting_search_v2.', 'evidence_refs': []}
    traj = trace.get('trajectory', []) or []
    text_blob = ''
    for step in traj:
        c = step.get('content')
        if isinstance(c,str): text_blob += '\n' + c
    cache_pat = re.compile(r'cache|disk|project[_ -]?key|write.*file|saved? to|persist', re.I)
    evidence = bool(cache_pat.search(text_blob))
    cache_tool = any(re.search(r'cache|write|save|persist|disk', (c.get('name') or ''), re.I) for c in calls)
    if evidence or cache_tool:
        return {'observed_followed': True, 'confidence': 'low', 'reason': 'Found textual/tool evidence of caching before cross-tool comparison.', 'evidence_refs': []}
    return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No observable evidence of disk caching under project key; cannot verify from trace.', 'evidence_refs': []}
