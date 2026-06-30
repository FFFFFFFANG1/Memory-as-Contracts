def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls') or []
    final = (trace.get('final_response') or '').strip()
    allowed = 'election_result_finder'
    used = [tc.get('name') for tc in tool_calls]
    other = [n for n in used if n and n != allowed]
    if other:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Used non-allowed tools: {sorted(set(other))}', 'evidence_refs': []}
    if not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response to inspect for jurisdiction citation.', 'evidence_refs': []}
    # Look for jurisdiction hint: explicit label or capitalized place name patterns
    juris_terms = ['jurisdiction', 'precinct', 'county', 'district', 'state', 'province', 'municipality', 'city', 'country', 'constituency', 'ward', 'region']
    text_lower = final.lower()
    has_label = any(t in text_lower for t in juris_terms)
    # Also accept patterns like 'in <Capitalized Place>'
    place_pat = re.search(r'\b(?:in|for|of)\s+([A-Z][A-Za-z\.\-]+(?:\s+[A-Z][A-Za-z\.\-]+){0,3})', final)
    if has_label or place_pat:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Only election_result_finder used (or no tools) and response references a polling jurisdiction.', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Response does not appear to cite a polling jurisdiction.', 'evidence_refs': []}
