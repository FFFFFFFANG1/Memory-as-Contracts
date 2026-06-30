def evaluate(trace):
    import re
    calls = trace.get('tool_calls') or []
    mentor_calls = [c for c in calls if c.get('name') == 'artist_mentor_finder']
    if len(mentor_calls) != 1:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'artist_mentor_finder called {len(mentor_calls)} times, expected 1', 'evidence_refs': []}
    final = trace.get('final_response') or ''
    if not final.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty final response', 'evidence_refs': []}
    has_mentor_tag = bool(re.search(r'<\s*mentor\b[^>]*>.*?<\s*/\s*mentor\s*>', final, re.DOTALL | re.IGNORECASE))
    if not has_mentor_tag:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no <mentor> XML element found in final response', 'evidence_refs': []}
    stripped = final.strip()
    looks_json = stripped.startswith('{') or stripped.startswith('[')
    if looks_json:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'final response appears to be JSON serialized', 'evidence_refs': []}
    fenced_json = re.search(r'```\s*json', final, re.IGNORECASE)
    if fenced_json:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'final response contains a JSON code block', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'single artist_mentor_finder call and result wrapped in <mentor> XML without JSON', 'evidence_refs': []}
