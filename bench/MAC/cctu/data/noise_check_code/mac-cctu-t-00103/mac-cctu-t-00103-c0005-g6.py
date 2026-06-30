def evaluate(trace):
    import re
    final = (trace.get('final_response') or '')
    calls = trace.get('tool_calls') or []
    lib_calls = [c for c in calls if (c.get('name') or '') == 'library_catalog_query']
    if not lib_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No library_catalog_query calls found; constraint not triggered or no evidence.', 'evidence_refs': []}
    text = final.lower()
    # Check for thousands normalization indicator
    has_thousands = bool(re.search(r'(thousand|\bk\b|,000|in thousands|\(000s?\)|holdings.*thousand)', text))
    # Check for any number followed by k or thousand near 'holdings' or 'catalog'
    if not has_thousands:
        has_thousands = bool(re.search(r'\d+(?:\.\d+)?\s*(k|thousand)', text))
    # Check for timestamp evidence
    has_timestamp = bool(re.search(r'\d{4}-\d{2}-\d{2}|\d{2}:\d{2}|timestamp|retrieved (at|on)|as of', text, re.I))
    if has_thousands and has_timestamp:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Final response contains thousands normalization and a retrieval timestamp.', 'evidence_refs': []}
    missing = []
    if not has_thousands: missing.append('thousands normalization')
    if not has_timestamp: missing.append('retrieval timestamp')
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Missing: ' + ', '.join(missing), 'evidence_refs': []}
