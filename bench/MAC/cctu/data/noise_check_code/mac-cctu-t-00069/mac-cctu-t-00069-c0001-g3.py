def evaluate(trace):
    import json, re
    tcs = trace.get('tool_calls') or []
    final = trace.get('final_response') or ''
    if not tcs and not final.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no evidence', 'evidence_refs': []}
    first_ok = None
    if tcs:
        try:
            first = sorted(tcs, key=lambda c: (c.get('iteration', 0), c.get('index', 0)))[0]
            first_ok = (first.get('name') == 'artist_artwork_identifier')
        except BaseException as e:
            first_ok = None
    parsed = None
    s = final.strip()
    try:
        parsed = json.loads(s)
    except BaseException:
        m = re.search(r'\{.*\}', s, re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group(0))
            except BaseException:
                parsed = None
    fmt_ok = isinstance(parsed, dict) and 'artist' in parsed and 'work' in parsed
    if first_ok is None and not final.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'insufficient evidence', 'evidence_refs': []}
    followed = bool(first_ok) and bool(fmt_ok) if tcs else bool(fmt_ok)
    reason = 'first_tool_ok=' + str(first_ok) + '; json_keys_ok=' + str(fmt_ok)
    return {'observed_followed': followed, 'confidence': 'high', 'reason': reason, 'evidence_refs': []}
