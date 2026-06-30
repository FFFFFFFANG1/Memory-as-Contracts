def evaluate(trace):
    import re
    allowed = {'business_district_locator','city_district_locator','nearby_road_locator'}
    calls = trace.get('tool_calls') or []
    used = [c.get('name') for c in calls if c.get('name')]
    bad = [n for n in used if n not in allowed]
    final = trace.get('final_response') or ''
    # numbered shortlist detection: lines beginning with '1.' and '2.' etc.
    lines = [l.strip() for l in final.splitlines() if l.strip()]
    numbered = [l for l in lines if re.match(r'^\d+[\.\)]\s+', l)]
    has_shortlist = len(numbered) >= 2
    if bad:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Used disallowed tools: {sorted(set(bad))}', 'evidence_refs': []}
    if not has_shortlist:
        if not final.strip():
            return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response to check for numbered shortlist', 'evidence_refs': []}
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Final response lacks a numbered shortlist (>=2 numbered items)', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'Only allowed tools used and a numbered shortlist is present', 'evidence_refs': []}
