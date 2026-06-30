def evaluate(trace):
    import re
    allowed = {'historical_landmark_locator','attraction_locator','cultural_geography_locator'}
    calls = trace.get('tool_calls') or []
    used = [c.get('name') for c in calls if c.get('name')]
    forbidden_used = [n for n in used if n not in allowed]
    resp = trace.get('final_response') or ''
    lines = [l.strip() for l in resp.splitlines() if l.strip()]
    numbered = [l for l in lines if re.match(r'^\(?\d+[\.\)]\s+\S', l)]
    has_numbered_list = len(numbered) >= 2
    if forbidden_used:
        return {'observed_followed': False, 'confidence':'high','reason': f'used forbidden tools: {forbidden_used}', 'evidence_refs':[]}
    if not resp.strip():
        return {'observed_followed': None,'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    if not has_numbered_list:
        return {'observed_followed': False,'confidence':'medium','reason':'response is not a numbered list','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'medium','reason':'only allowed tools used and response is a numbered prose list','evidence_refs':[]}
