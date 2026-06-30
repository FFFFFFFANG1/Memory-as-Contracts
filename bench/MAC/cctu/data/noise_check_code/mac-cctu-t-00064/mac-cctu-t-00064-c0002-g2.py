def evaluate(trace):
    import re
    allowed = {'quarry_locator','mountain_quarry_locator'}
    calls = trace.get('tool_calls') or []
    used = [c.get('name') for c in calls]
    disallowed = [n for n in used if n and n not in allowed]
    if disallowed:
        return {'observed_followed': False, 'confidence':'high', 'reason': f'Used disallowed tools: {sorted(set(disallowed))}', 'evidence_refs':[]}
    if not used:
        return {'observed_followed': None, 'confidence':'low', 'reason':'No tool calls present to evaluate', 'evidence_refs':[]}
    final = trace.get('final_response') or ''
    combined = final + '\n' + '\n'.join(str(c.get('result','')) for c in calls)
    coord_pat = re.compile(r'[-+]?\d{1,3}\.\d+\s*[,\s]\s*[-+]?\d{1,3}\.\d+')
    dms_pat = re.compile(r'\d+\s*\xb0\s*\d+', re.IGNORECASE)
    has_coords = bool(coord_pat.search(combined) or dms_pat.search(combined) or re.search(r'lat(itude)?', combined, re.I))
    if not has_coords:
        return {'observed_followed': False, 'confidence':'medium', 'reason':'No raw geographic coordinates found in trajectory/response', 'evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'high', 'reason':'Only allowed quarry tools used and coordinates recorded', 'evidence_refs':[]}
