def evaluate(trace):
    import re
    calls = trace.get('tool_calls') or []
    allowed = 'medical_event_finder'
    forbidden_used = [c.get('name') for c in calls if c.get('name') and c.get('name') != allowed]
    final = trace.get('final_response') or ''
    has_pipe_table = bool(re.search(r'^\s*\|.*\|\s*$', final, re.MULTILINE)) and bool(re.search(r'^\s*\|?\s*[:\- ]+\|[:\- |]+\s*$', final, re.MULTILINE))
    has_html_table = bool(re.search(r'<table[\s>]', final, re.IGNORECASE))
    tabular = has_pipe_table or has_html_table
    if forbidden_used:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Used disallowed tools: {sorted(set(forbidden_used))}', 'evidence_refs': []}
    if tabular:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Final response contains tabular output', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Only medical_event_finder used (or no tools) and no table detected', 'evidence_refs': []}
