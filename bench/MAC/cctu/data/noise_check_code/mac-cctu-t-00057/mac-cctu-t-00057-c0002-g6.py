def evaluate(trace):
    import json, re
    tool_calls = trace.get('tool_calls', []) or []
    lml = [c for c in tool_calls if (c.get('name') or '') == 'library_manuscript_locator']
    count_ok = len(lml) >= 2
    final = trace.get('final_response', '') or ''
    parsed = None
    try:
        parsed = json.loads(final)
    except Exception:
        m = re.search(r'\{.*\}', final, re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group(0))
            except Exception:
                parsed = None
    is_json_obj = isinstance(parsed, dict)
    has_hop_keys = False
    if is_json_obj and parsed:
        keys = [str(k).lower() for k in parsed.keys()]
        has_hop_keys = any('hop' in k for k in keys)
    if not count_ok and not is_json_obj:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'library_manuscript_locator called {len(lml)} times and final response is not a JSON object', 'evidence_refs': []}
    if not count_ok:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'library_manuscript_locator called only {len(lml)} time(s); need >=2', 'evidence_refs': []}
    if not is_json_obj:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'final response is not a JSON object keyed by hop name', 'evidence_refs': []}
    if not has_hop_keys:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'JSON object present but no key appears to reference a hop name', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'library_manuscript_locator called {len(lml)} times and final response is a JSON object keyed by hop name', 'evidence_refs': []}
