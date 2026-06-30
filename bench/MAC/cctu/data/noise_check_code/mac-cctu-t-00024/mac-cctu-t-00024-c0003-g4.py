def evaluate(trace):
    import re, json
    allowed = {'price_comparison_tool'}
    calls = trace.get('tool_calls') or []
    bad = [c.get('name') for c in calls if c.get('name') and c.get('name') not in allowed]
    final = trace.get('final_response') or ''
    if bad:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Used disallowed tools: {bad}', 'evidence_refs': []}
    if not final.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response', 'evidence_refs': []}
    obj = None
    try:
        obj = json.loads(final)
    except Exception:
        m = re.search(r'\{.*\}', final, re.S)
        if m:
            try:
                obj = json.loads(m.group(0))
            except Exception:
                obj = None
    if not isinstance(obj, dict):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Final response is not a JSON object', 'evidence_refs': []}
    if 'price_usd' not in obj:
        return {'observed_followed': False, 'confidence': 'high', 'reason': "Missing 'price_usd' key", 'evidence_refs': []}
    val = obj['price_usd']
    def ok(v):
        if isinstance(v, str):
            return bool(re.fullmatch(r'-?\d+\.\d{2}', v.strip().lstrip('$').replace(',', '')))
        if isinstance(v, (int, float)):
            return False
        return False
    vals = val if isinstance(val, list) else [val]
    for v in vals:
        if not ok(v):
            return {'observed_followed': False, 'confidence': 'high', 'reason': f'price_usd not formatted to 2 decimals as string: {v!r}', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'Only price_comparison_tool used and price_usd formatted to 2 decimals', 'evidence_refs': []}
