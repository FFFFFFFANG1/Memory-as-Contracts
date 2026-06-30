def evaluate(trace):
    import re, json
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    if len(tool_calls) <= 1:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'Not enough tool calls to assess caching between calls.', 'evidence_refs': []}
    # Look for JSON cache persistence between tool calls in assistant content
    cache_hits = 0
    needed = max(0, len(tool_calls) - 1)
    for step in traj:
        content = (step.get('content') or '') if isinstance(step, dict) else ''
        if not content:
            continue
        low = content.lower()
        mentions_cache = any(k in low for k in ['cache', 'persist', 'store', 'save', 'memo'])
        has_json_block = False
        for m in re.findall(r'\{[\s\S]*?\}', content):
            try:
                obj = json.loads(m)
                if isinstance(obj, (dict, list)):
                    has_json_block = True
                    break
            except Exception:
                pass
        if mentions_cache and has_json_block:
            cache_hits += 1
    if cache_hits == 0:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'No JSON cache persistence detected between tool calls.', 'evidence_refs': []}
    if cache_hits >= needed:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': f'Found {cache_hits} JSON cache persistence steps for {needed} inter-call gaps.', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'low', 'reason': f'Only {cache_hits} cache persistence steps for {needed} required gaps.', 'evidence_refs': []}
