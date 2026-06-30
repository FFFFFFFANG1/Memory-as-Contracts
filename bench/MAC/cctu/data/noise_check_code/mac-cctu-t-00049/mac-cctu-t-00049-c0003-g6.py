def evaluate(trace):
    import re
    allowed = {'space_mission_info_retriever', 'astronomical_discovery_finder'}
    tool_calls = trace.get('tool_calls') or []
    used = [tc.get('name') for tc in tool_calls if tc.get('name')]
    forbidden_used = [n for n in used if n not in allowed]
    if forbidden_used:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Used disallowed tools: {sorted(set(forbidden_used))}', 'evidence_refs': []}
    final = trace.get('final_response') or ''
    if not final.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response to inspect', 'evidence_refs': []}
    # Find ISO-8601 dates (YYYY, YYYY-MM, YYYY-MM-DD)
    iso_pattern = re.compile(r'\b(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?\b')
    matches = iso_pattern.findall(final)
    if not matches:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'No ISO-8601 dates found in final response', 'evidence_refs': []}
    # Build sortable keys
    def key(m):
        y = int(m[0]); mo = int(m[1]) if m[1] else 1; d = int(m[2]) if m[2] else 1
        return (y, mo, d)
    keys = [key(m) for m in matches]
    if keys != sorted(keys):
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'ISO dates not in ascending order: {keys}', 'evidence_refs': []}
    # Also check for non-ISO date formats that might indicate violation
    non_iso = re.findall(r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b', final, re.IGNORECASE)
    slash = re.findall(r'\b\d{1,2}/\d{1,2}/\d{2,4}\b', final)
    if non_iso or slash:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Non-ISO date formats present alongside required ISO format', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'Only allowed tools used; final response has ISO-8601 dates in ascending order', 'evidence_refs': []}
