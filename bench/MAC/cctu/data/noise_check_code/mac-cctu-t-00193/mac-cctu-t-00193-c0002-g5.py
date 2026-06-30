def evaluate(trace):
    import re
    calls = trace.get('tool_calls', []) or []
    rhl = [c for c in calls if (c.get('name') or '') == 'region_highlight_locator']
    final = trace.get('final_response') or ''
    if not rhl:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'region_highlight_locator was never invoked', 'evidence_refs': []}
    # Try to find festival events referenced in the response or other tool calls
    festival_mentions = len(re.findall(r'(?i)festival', final))
    has_index = bool(re.search(r'(?i)tourism\s*index', final)) or bool(re.search(r'(?i)regional\s+tourism', final))
    if festival_mentions == 0:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'No festival events detected in final response to cross-reference', 'evidence_refs': []}
    if len(rhl) < festival_mentions:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Found {festival_mentions} festival mentions but only {len(rhl)} region_highlight_locator calls', 'evidence_refs': [f'rhl_calls={len(rhl)}']}
    if not has_index:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Tourism index not attached in final response', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'region_highlight_locator used per festival and tourism index attached', 'evidence_refs': [f'rhl_calls={len(rhl)}']}
